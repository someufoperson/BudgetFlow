# Architecture

**The system consists of the following components:**

1. Python (a convenient, user-friendly, and popular programming language. The project can be edited by an ordinary user who knows the basic syntax of Python)
2. Requests (single-user programs do not have strict requirements for code execution speed; everything is executed sequentially)
3. SQLite3 (raising a full-fledged PostgreSQL or similar DBMS is overengineering within this project)
4. Pydantic (convenient validation of incoming and outgoing data with flexible customization)

**The main path of requests to AI is as follows:**

User request -> AI reads the list of available tools -> calls one of the tools -> generates a response with reliable validation or makes changes to the database -> sends the response to the user
