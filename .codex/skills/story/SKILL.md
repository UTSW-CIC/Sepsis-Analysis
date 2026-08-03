---
name: story
description: Generate Agile user stories and split them into development tasks with hours and priority.
---

# Skill: Agile Story Generator

## Purpose

Generate clear Agile user stories and split each story into actionable development tasks with estimated working hours and priority.

## When to use this skill

Use this skill when the user asks to create, refine, or break down Agile stories, features, epics, requirements, or product ideas into stories and tasks.

## Input expected from user

The user may provide one or more of the following:

- Feature name
- Product requirement
- Epic description
- User goal
- Business objective
- Technical requirement
- Existing story draft

If information is missing, make reasonable assumptions and clearly state them.

## Output format

For each Agile story, generate the following format exactly:

```text
Title:
Description:
Acceptance criteria:
Story hours:
```

Then split each story into tasks using the following format exactly:
```text
title:
Description:
working hours:
Priority:

Priority must be between 1 and 4:

1: Critical
2: High
3: Medium
4: Low
```

## Story generation rules
When creating a story:

1. Use a concise and meaningful title.

2. Write the description as a user story when possible:
```text
As a [user/persona], I want [goal], so that [benefit].
```
3. Acceptance criteria should be clear, testable, and preferably written as bullet points.

4. Use Given / When / Then format where useful.

5. Estimate story hours realistically.

6. If multiple stories are needed, split them by user value or functional boundary.

7. Avoid overly large stories. If a story is too broad, split it into smaller stories.

8. Include assumptions if required.

## Task generation rules
For each story:

1. Split the story into practical tasks.
2. Tasks should be small enough to complete independently.
3. Include backend, database, API, testing, documentation, or DevOps tasks where relevant.
4. Assign realistic working hours to each task.
5. Assign a priority from 1 to 4.
6. Critical path or blocking work should have priority 1.
7. Nice-to-have or cleanup tasks should have priority 4.

## Output behavior
When the user asks to generate stories:

1. Generate the Agile stories.
2. Create the Stories directory if needed.
3. Write each story into its own Markdown file.
4. After creating the files, respond with a concise summary listing the created files.

Example response:
```text
Created the following story files:

- Stories/user-login.md
- Stories/password-reset.md
- Stories/manage-user-notifications.md
```

## Example generated file
File
```text
Stories/user-login.md
```

```text
# User Login

**Creation date:** 2026-07-28

## Description

As a registered user, I want to log in using my email and password, so that I can securely access my account.

## Acceptance criteria

- Given a registered user, when they enter a valid email and password, then they should be logged in successfully.
- Given an invalid password, when the user attempts to log in, then an error message should be displayed.
- Given an unregistered email, when the user attempts to log in, then the system should show an appropriate error.
- The user session should be created after successful login.
- Passwords must not be exposed in logs or responses.

## Story hours

16

## Tasks

### Task 1: Create login API endpoint

**Description:**  
Implement a backend endpoint to authenticate users using email and password.

**Working hours:** 4

**Priority:** 1

### Task 2: Validate login request

**Description:**  
Add validation for required fields, email format, and empty password values.

**Working hours:** 2

**Priority:** 1

### Task 3: Implement session or token generation

**Description:**  
Generate a secure user session or authentication token after successful login.

**Working hours:** 3

**Priority:** 1

### Task 4: Build login UI form

**Description:**  
Create the frontend login form with email and password fields and a submit button.

**Working hours:** 3

**Priority:** 2

### Task 5: Display login error messages

**Description:**  
Show user-friendly error messages for invalid credentials or failed login attempts.

**Working hours:** 2

**Priority:** 2

### Task 6: Add login tests

**Description:**  
Add unit and integration tests for successful login, invalid credentials, and missing fields.

**Working hours:** 2

**Priority:** 2
```

### Final instruction
Whenever the user provides a requirement, generate Agile stories and tasks using only the required formats unless the user asks for additional explanation.

