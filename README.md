# BudgetFlow

The BudgetFlow project aims to help users manage and plan their budgets using AI tools.

 Most people do not keep track of their financial flows, do not control their purchases based on emotions, and do not plan their budgets for months or years ahead. This is because people find it difficult to act in challenging circumstances or simply do not know about financial literacy.

 The project itself plans to implement features that can help users get out of debt, create a reliable deposit system, build a budgeting strategy, analyze expenses and income, and provide psychological support during difficult times, emphasizing the importance of financial literacy.

In the future, the system is planned in such a way that a person would record their expenses every day, clearly understand where their money comes from, and be able to ask AI, "Can I afford a new iPhone that costs $1,200?" and receive an honest answer, "Yes, but you'll have to start saving money until your next paycheck."

*"Beware of small expenses; a small leak will sink a large ship"* -  Benjamin Franklin.
___
**BudgeFlow currently has the following features:**

1. Minimalistic CLI interface
2. Adding incoming and expense transaction with automatically determined names, amounts and type transaction using AI
___
**TODO**
- [ ] 👾 User interface: creating a web form for easy display of transaction information, strategy, debt obligations, and budget expectations. Additionally, creating a CLI interface similar to Claude Code or Codex CLI
- [ ] 🤖 AI: analysis of expenses and revenues, building budget expectations, recommendations for individual purchases, building and maintaining a budget management strategy
- [ ] 👤 Personalization: taking into account your preferences, goals for saving money, debt obligations, and expected expenses and income
- [ ] 💰 Budget: debt accounting, interest on deposits, cryptocurrency deposits, and assistance in managing all financial instruments, including assistance in getting out of debt holes
- [ ] 🔐 Security: secure local storage of user data and masking of sensitive data when using the AI interface from vendors

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