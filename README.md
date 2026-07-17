# BudgetFlow

AI support for your personal finance flows
___
**BudgeFlow currently has the following features:**

1. Minimalistic CLI interface
2. Adding incoming and expense transaction with automatically determined names, amounts and type transaction using AI
___
**TODO**
- [ ] Create a tool for displaying all transactions with filtering by date and other parameters
- [ ] Creating a user interface other than the CLI
- [ ] AI should analyze your spending and provide budgeting advice

___
**Quick Start**

You need to create a .env file using the .env.example template and add your own constants

After that you need to create virtual environment and install the dependencies

Without uv:
- Create virtual environment using command `python -m venv venv`
- Activate virtual environment using command `venv\Scripts\activate`
- Install the dependencies using command `python -m pip install -e .`

With uv:
- Use command `uv sync` for create virtual environment and install dependencies 

Activate your virtual environment if you haven't done so already using the `venv\Scripts\activate` command

Success! Launch the script using command `python main.py` and start managing your personal budget the BudgetFlow AI Tool