<!---
This contributing file takes inspiration from
https://github.com/Rapptz/discord.py/blob/425edd2e10b9be3d7799c0df0cd1d43a1a34654e/.github/CONTRIBUTING.md
--->
## Contributing to Oi
Below are the guidelines on how to contribute to Oi.

### Issues
You should open an issue when you:
- find a bug
- have a suggestion
- have an inquiry

Before you open an issue, make sure there are no open issues that are similar to your issue.

#### Bug Report Guidelines
- Title your issue a brief summary of your issue.
- In the description:
  - Write a detailed summary of your issue.
  - Include screenshots if possible.
  - Explain how to reproduce the bug.
  - Do NOT say "it doesn't work". Instead, explain **what happened**, and what you **expected to happen**.


#### Feature Request Guidelines
- Title your request with what feature you are requesting.
- In the description:
  - Explain what the feature will do, in detail so that we can determine if this feature should be added.
  - Features that have anything to do with [privileged intents](https://discord.com/developers/docs/topics/gateway#privileged-intents) will not be added, as Oi does not have access to them.


Failure to follow these guidelines will result in your issue being closed.

### Pull Requests
Ensure your contribution follows the code style in this project. This project uses [black](https://github.com/psf/black) and [isort](https://github.com/PyCQA/isort) for code format. [Ruff](https://github.com/astral-sh/ruff) and [pyright](https://github.com/microsoft/pyright) is used for linting and type-checking. Use these tools configured the same way as found in the [`pyproject.toml`](/pyproject.toml) file.

#### Git Commit Guidelines
Try your best to follow these guidelines as follows:
- Use present-tense (ex: `Fix music`, `Add checks` not `Fixed music`, `Added Checks`)
- Commit Comments:
  - Keep first line under 50 characters
  - Limit the rest of the lines under 70 characters

If you don't follow these guidelines, it's okay. They will be fixed upon rebasing.