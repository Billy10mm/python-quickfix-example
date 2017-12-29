#!/your/path/to/python2.7

import quickfix
import sys
import texttable
import threading

class FIXServer(quickfix.Application):
    def onCreate(self, session):
        targetCompID = session.getTargetCompID().getValue()
        try:
            self.sessions[targetCompID] = {}
        except AttributeError:
            # We're here if this is the first connected session, so we initialize everything.
            # I wouldn't have to do this wonky crap if quickfix.Application didn't hijack __init__()
            self.lastOrderID            = 0
            self.sessions               = {}
            self.orders                 = {}
            self.sessions[targetCompID] = {}

        self.sessions[targetCompID]['session']   = session
        self.sessions[targetCompID]['connected'] = False
        self.sessions[targetCompID]['exchID']    = 0
        self.sessions[targetCompID]['execID']    = 0

    def onLogon(self, session):
        targetCompID                             = session.getTargetCompID().getValue()
        self.sessions[targetCompID]['connected'] = True
        print "\nClient {} has logged in\n--> ".format(targetCompID),

    def onLogout(self, session):
        targetCompID                             = session.getTargetCompID().getValue()
        self.sessions[targetCompID]['connected'] = False
        print "\nClient {} has logged out\n--> ".format(targetCompID),

    def toAdmin(self, session, message):
        return

    def fromAdmin(self, session, message):
        return

    def toApp(self, session, message):
        return

    def fromApp(self, message, session):
        clientOrderID = self.getValue(message, quickfix.ClOrdID())
        targetCompID  = session.getTargetCompID().getValue()
        details       = {'session'  : session,
                         'clOrdID'  : clientOrderID,
                         'target'   : targetCompID,
                         'symbol'   : self.getValue(message, quickfix.Symbol()),
                         'side'     : self.getValue(message, quickfix.Side()),
                         'sideStr'  : self.getSide(self.getValue(message, quickfix.Side())),
                         'quantity' : self.getValue(message, quickfix.OrderQty()),
                         'leaves'   : self.getValue(message, quickfix.OrderQty())}

        if self.getHeaderValue(message, quickfix.MsgType()) == quickfix.MsgType_NewOrderSingle:
            ## Received new order from client
            orderID = self.getNextOrderID()
            print "\nNewOrder {} received\n--> ".format(orderID),
            details['ordType'] = self.getValue(message, quickfix.OrdType())
            details['state']   = 'PendingAck'

            if (self.getValue(message, quickfix.OrdType()) == quickfix.OrdType_LIMIT or
                    self.getValue(message, quickfix.OrdType()) == quickfix.OrdType_LIMIT_ON_CLOSE):
                # Limit orders will have a price, Market order will not.
                details['price'] = self.getValue(message, quickfix.Price())

            self.orders[orderID] = details
            self.sessions[targetCompID][clientOrderID] = orderID

        if self.getHeaderValue(message, quickfix.MsgType()) == quickfix.MsgType_OrderCancelRequest:
            origClientOrderID      = self.getValue(message, quickfix.OrigClOrdID())
            details['origClOrdID'] = origClientOrderID
            details['cxlClOrdID']  = clientOrderID

            if origClientOrderID not in self.sessions[targetCompID]:
                # A cancel request has come in for an order we don't have in the book
                # So let's create that order in the book based on what we know
                orderID                                        = self.getNextOrderID()
                self.orders[orderID]                           = details
                self.sessions[targetCompID][origClientOrderID] = orderID
            else:
                ## We have the order in the book
                orderID = self.sessions[targetCompID][origClientOrderID]
                self.orders[orderID]['cxlClOrdID']   = clientOrderID

            self.orders[orderID]['state']      = 'PendingCancel'
            print "\nCancelRequest for OrderID {} received\n--> ".format(orderID),

        if self.getHeaderValue(message, quickfix.MsgType()) == quickfix.MsgType_OrderCancelReplaceRequest:
            origClientOrderID = self.getValue(message, quickfix.OrigClOrdID())

            if origClientOrderID not in self.sessions[targetCompID]:
                ## A replace request has come in for an order we don't have in the book
                orderID                                        = self.getNextOrderID()
                self.orders[orderID]                           = details
                self.sessions[targetCompID][origClientOrderID] = orderID

            else:
                ## We have the original order in the book
                orderID = self.sessions[targetCompID][origClientOrderID]

            self.orders[orderID]['rplClOrdID'] = clientOrderID
            self.orders[orderID]['state']      = 'PendingReplace'

            newOrderID = self.getNextOrderID()
            self.orders[newOrderID]                = details
            self.orders[newOrderID]['origClOrdID'] = origClientOrderID
            self.orders[newOrderID]['origOrdID']   = orderID
            self.orders[newOrderID]['state']    = 'PendingNew'
            print "OrderID {} to replace OrderID {} received\n--> ".format(newOrderID, orderID),

    def getNextOrderID(self):
        self.lastOrderID += 1
        return self.lastOrderID

    def getNextExecID(self, targetCompID):
        self.sessions[targetCompID]['execID'] += 1
        return "{}_{}".format(targetCompID, self.sessions[targetCompID]['execID'])

    def getNextExchangeID(self, targetCompID):
        self.sessions[targetCompID]['exchID'] += 1
        return "{}_{}".format(targetCompID, self.sessions[targetCompID]['exchID'])

    def startFIXString(self, orderID):
        message = quickfix.Message()
        message.getHeader().setField(quickfix.BeginString(quickfix.BeginString_FIX42))
        message.getHeader().setField(quickfix.MsgType(quickfix.MsgType_ExecutionReport))
        message.getHeader().setField(quickfix.SendingTime())
        message.getHeader().setField(quickfix.TransactTime())
        message.setField(quickfix.ClOrdID(self.orders[orderID]['clOrdID']))
        message.setField(quickfix.OrderQty(self.orders[orderID]['quantity']))
        message.setField(quickfix.Symbol(self.orders[orderID]['symbol']))
        message.setField(quickfix.Side(self.orders[orderID]['side']))
        message.setField(quickfix.ExecID(str(self.getNextExecID(self.orders[orderID]['target']))))
        if 'exchangeID' not in self.orders[orderID]:
            self.orders[orderID]['exchangeID'] = self.getNextExchangeID(self.orders[orderID]['target'])
        message.setField(quickfix.OrderID(str(self.orders[orderID]['exchangeID'])))
        return message

    def sendOrderAck(self, orderID):
        message = self.startFIXString(orderID)
        message.setField(quickfix.ExecType(quickfix.ExecType_NEW))
        message.setField(quickfix.ExecTransType(quickfix.ExecTransType_NEW))

        quickfix.Session.sendToTarget(message, self.orders[orderID]['session'])
        self.orders[orderID]['state'] = 'New'

    def sendCancelAck(self, orderID):
        message = self.startFIXString(orderID)
        message.setField(quickfix.OrderQty(self.orders[orderID]['leaves']))
        message.setField(quickfix.ExecType(quickfix.ExecType_CANCELED))
        if 'cxlClOrdID' in self.orders[orderID]:
            message.setField(quickfix.ClOrdID(self.orders[orderID]['cxlClOrdID']))
        if 'origClOrdID' in self.orders[orderID]:
            message.setField(quickfix.OrigClOrdID(self.orders[orderID]['origClOrdID']))
        else:
            message.setField(quickfix.OrigClOrdID(self.orders[orderID]['clOrdID']))
        quickfix.Session.sendToTarget(message, self.orders[orderID]['session'])
        self.orders[orderID]['state'] = 'Canceled'

    def sendReplaceAck(self, orderID):
        origOrdID         = self.orders[orderID]['origOrdID']
        origClientOrderID = self.orders[orderID]['origClOrdID']
        message = self.startFIXString(orderID)
        message.setField(quickfix.OrderQty(self.orders[orderID]['quantity']))
        message.setField(quickfix.ExecType(quickfix.ExecType_REPLACED))
        message.setField(quickfix.ExecTransType(quickfix.ExecTransType_NEW))
        message.setField(quickfix.OrigClOrdID(origClientOrderID))

        quickfix.Session.sendToTarget(message, self.orders[orderID]['session'])
        self.orders[orderID]['state']   = 'New'
        self.orders[origOrdID]['state'] = 'Replaced'

    def sendReplacePending(self, orderID):
        origClientOrderID = self.orders[orderID]['origClOrdID']
        message = self.startFIXString(orderID)
        message.setField(quickfix.OrderQty(self.orders[orderID]['quantity']))
        message.setField(quickfix.ExecType(quickfix.ExecType_PENDING_REPLACE))
        message.setField(quickfix.OrigClOrdID(origClientOrderID))

        quickfix.Session.sendToTarget(message, self.orders[orderID]['session'])

    def sendFill(self, orderID, quantity):
        message = self.startFIXString(orderID)
        if self.orders[orderID]['leaves'] <= quantity:
            message.setField(quickfix.OrdStatus(quickfix.OrdStatus_FILLED))
            message.setField(quickfix.ExecType(quickfix.ExecType_FILL))
        else:
            message.setField(quickfix.OrdStatus(quickfix.OrdStatus_PARTIALLY_FILLED))
            message.setField(quickfix.ExecType(quickfix.ExecType_PARTIAL_FILL))
        message.setField(quickfix.LastShares(quantity))
        if 'price' in self.orders[orderID]:
            message.setField(quickfix.LastPx(self.orders[orderID]['price']))
        else:
            message.setField(quickfix.LastPx(1.00))
        quickfix.Session.sendToTarget(message, self.orders[orderID]['session'])
        self.orders[orderID]['leaves'] -= quantity
        if self.orders[orderID]['leaves'] < 1:
            self.orders[orderID]['state'] = 'Filled'

    def getHeaderValue(self, message, field):
        key = field
        message.getHeader().getField(key)
        return key.getValue()

    def getValue(self, message, field):
        key = field
        message.getField(key)
        return key.getValue()

    def getFooterValue(self, message, field):
        key = field
        message.getTrailer().getField(key)
        return key.getValue()

    def showOrders(self):
        if len(self.orders) > 0:
            table = texttable.Texttable()
            table.header(['OrderID', 'Client', 'ClOrdID', 'Side', 'OrdQty', 'Leaves', 'Symbol', 'State'])
            table.set_cols_width([8, 12, 16, 8, 12, 12, 12, 32])
            for order in self.orders:
                table.add_row([order,
                               self.orders[order]['target'],
                               self.orders[order]['clOrdID'],
                               self.orders[order]['sideStr'],
                               self.orders[order]['quantity'],
                               self.orders[order]['leaves'],
                               self.orders[order]['symbol'],
                               self.orders[order]['state']])
            print table.draw()
        else:
            print "The order book is currently empty"

    def getSide(self, side):
        if side == '1': return "Buy"
        if side == '2': return "Sell"
        if side == '5': return "SellShort"

    def getOrderDetails(self, orderID):
        table = texttable.Texttable()
        table.set_cols_width([16, 32])
        for key in self.orders[orderID]:
            table.add_row([key, self.orders[orderID][key]])
        print table.draw()


if len(sys.argv) > 1:
    configFile = sys.argv[1]
else:
    configFile = 'mfs-quickfix.cfg'
settings     = quickfix.SessionSettings(configFile)
application  = FIXServer()
logFactory   = quickfix.ScreenLogFactory(settings)
storeFactory = quickfix.FileStoreFactory(settings)
acceptor     = quickfix.SocketAcceptor(application, storeFactory, settings)
fixServer    = threading.Thread(target=acceptor.start())
fixServer.start()

def help():
    print "Commands are: "
    print "\tbook                       ## Shows current order book"
    print "\tack [orderID]              ## Sends acknowledgement on orderID"
    print "\tcancel [orderID]           ## Sends cancel ack on orderID"
    print "\tfill [orderID] [quantity]  ## Sends a fill on orderID with quantity"
    print "\torder [orderID]            ## Provides details about the order"
    print "\tremove [orderID]           ## Removes the order from the book"
    print "\treplace [orderID]          ## Sends a ReplaceAck on orderID"
    print "\treplacepend [orderID]      ## Sends a ReplacePending message for orderID"
    print "\texit                       ## Shuts down this server"


while True:
    command = raw_input("--> ")

    if not command: pass

    elif command.lower() == "help": help()

    elif command.lower() == "book": application.showOrders()

    elif command.lower()[:6] == "order ":
        orderID = command[6:]
        if not orderID or int(orderID) not in application.orders:
            print "OrderID {} not found in book.  Please try again.".format(orderID)
            application.showOrders()
        else:
            application.getOrderDetails(int(orderID))

    elif command.lower()[:7] == "remove ":
        orderID = command[7:]
        if not orderID or int(orderID) not in application.orders:
            print "OrderID {} not found in book. Please try again".format(orderID)
            application.showOrders()
        else:
            del application.orders[int(orderID)]
            application.showOrders()

    elif command.lower()[:4] == "ack ":
        orderID = command[4:]
        if not orderID or int(orderID) not in application.orders:
            print "OrderID {} not found in book. Please try again".format(orderID)
            application.showOrders()
        else:
            application.sendOrderAck(int(orderID))
            print "Ack sent for orderID {}".format(orderID)

    elif command.lower()[:7] == "cancel ":
        orderID = command[7:]
        if not orderID or int(orderID) not in application.orders:
            print "OrderID {} not found in book. Please try again".format(orderID)
            application.showOrders()
        else:
            application.sendCancelAck(int(orderID))
            print "CancelAck sent for orderID {}".format(orderID)

    elif command.lower()[:8] == "replace ":
        orderID = command[8:]
        if not orderID or int(orderID) not in application.orders:
            print "OrderID {} not found in book. Please try again".format(orderID)
            application.showOrders()
        else:
            application.sendReplaceAck(int(orderID))
            print "ReplaceAck for orderID {}".format(orderID)

    elif command.lower()[:12] == "replacepend ":
        orderID = command[12:]
        if not orderID or int(orderID) not in application.orders:
            print "OrderID {} not found in book. Please try again".format(orderID)
            application.showOrders()
        else:
            application.sendReplacePending(int(orderID))
            print "ReplacePending for orderID {}".format(orderID)

    elif command.lower()[:5] == "fill ":
        fillCmd = command.lower().split(' ')
        if len(fillCmd) != 3:
            print "Invalid number of parameters"
            help()
            continue
        orderID = fillCmd[1]
        quantity = fillCmd[2]
        if int(orderID) not in application.orders:
            print "OrderID {} not found in book.  Please try again".format(orderID)
            application.showOrders()
            continue
        try:
            application.sendFill(int(orderID), int(quantity))
            print "Fill of quantity {} sent for orderID {}".format(quantity, orderID)
        except:
            print "Quantity '{}' not a valid integer".format(quantity)
            help()

    elif command.lower() == 'exit': exit(0)

    else:
        print "Command '{}' invalid".format(command)
        help()
