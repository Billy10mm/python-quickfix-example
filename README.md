Example Python Quickfix Code that hopefully someone can use
===========================================

Had a helluva time finding Quickfix examples written in Python.  Finally got my project completed and figured if nothing else, some line in here might help someone else with their project.  That said, my code is crap.  I know that.  I can live with it.  I'm not a developer. All I did was stay at a Holiday Inn Express one night back in 2008.

If you want to run this thing as-is, here's a brief idea of what it does.  It's a FIX4.2 server that allows you to manually control your responses.  I built this to help troubleshoot a specific condition we were seeing in our trading platform because of one particular broker's craptastic FIX server.  Once launched (with the quickfix config file as a command-line param), it notifies you when clients connect and disconnect, and when they send orders, cancels, or replace requests.  It does not automatically respond to any of these, instead allowing you to react to these events how you want.  Typing "help" at the prompt lets you see your options:

    --> help
    Commands are:
        book                       ## Shows current order book
        ack [orderID]              ## Sends acknowledgement on orderID
        cancel [orderID]           ## Sends cancel ack on orderID
        fill [orderID] [quantity]  ## Sends a fill on orderID with quantity
        order [orderID]            ## Provides details about the orderID
        remove [orderID]           ## Removes the order from the book
        replace [orderID]          ## Sends a ReplaceAck on orderID
        replacepend [orderID]      ## Sends a ReplacePending message for orderID
        exit                       ## Shuts down this server

Some notes:
    - "orderID" in the commmand params is the orderID assigned, NOT the clientOrderID of the message received.
    - It supports multiple concurrent clients (nice!).
    - It has no logic for dealing with sequence number issues (not so nice)
    - If you have issues, I recommend clearing quickfix cache, setting seqnos to 1, and trying again
    - It doesn't automatically clear an order out of its book when the order is done, allowing you to send more messages back to the client if you want
