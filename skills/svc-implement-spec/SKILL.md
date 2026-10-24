---
name: svc-implement-spec
description: "Implement the result of /to-spec and /to-tickets in code."
disable-model-invocation: true
---

You have been provided a spec. This spec should have tickets associated with it, describing how to implement the spec.

The issue tracker should have been provided to you. If not, tell the user to run `/setup-matt-pocock-skills`.

The goal is the entire spec implemented on a single **integration branch**, with every ticket resolved the way the issue tracker closes work, the service tested locally end to end, and the code reviewed.

The tickets are not a list of steps. They are a **task graph** with blocking relationships between them. This means there is always a **frontier** of tickets which are ready to be grabbed.

Communication to and from subagents should be sparse. Communicate primarily through **context pointers**: to the spec, tickets, research notes, and previous commits. Don't duplicate information already available via pointers.

**Implementer subagents** should be run in the background where possible for maximum concurrency.

Local testing runs only on the integration branch, from the main agent: `svc-local-test-flow` stops for the user to confirm cases, and the local ports, database and Redis are shared by the whole machine, so one run at a time.

## Steps

1. Read the spec and tickets to understand the task graph.

2. (optional) Use an **exploration subagent** to conduct any exploration required by the tickets - relevant codebase files or external documentation. Ensure the exploration subagent can save files - it should save its markdown notes in a directory outside the repo, accessible by all future subagents. This lets **implementer subagents** focus on implementation rather than exploration.

3. Create the integration branch and note its base commit: it is the fixed point for every review below. If the issue tracker closes work through PRs, or the user asks for one, open a draft PR after the first merge in step 5 (a branch with no commits ahead of main can't open one), marked as closing the spec and tickets.

4. Use **implementer subagents** to implement each ticket, each in its own worktree on its own branch. Each implementer subagent:
   - confirms its worktree is based on the integration branch before starting, and resets onto it if not;
   - builds the ticket, running typechecking (`go build ./... && go vet ./...`) regularly and the existing test suite once at the end;
   - merges the integration branch tip into its own branch before reporting done.

5. Once an **implementer subagent** completes, merge its work to the integration branch with a **merger subagent**.

6. If this changes the **frontier** of available tickets, kick off more **implementer subagents** to work on the new tickets. This allows for maximum concurrency.

7. **Test.** Once all tickets are merged, check out the integration branch and call the Skill tool with `svc-local-test-flow` for each service the spec touches. Fix the failures it reports in a single **implementer subagent**, merge, and call `svc-local-test-flow` again (it picks the 同步 route for changed code).
   Done when every case passes, or the rest are blocked on the user.

8. **Review.** Call the Skill tool with `svc-code-review` on the integration branch, fixed point the base commit from step 3. Fix the issues it raises in a single **implementer subagent** and merge.
   Done when every issue is either fixed or explained to the user as left as is.

9. **Loop.** If step 8 changed any code, go back to step 7. Otherwise move on: the last test round passed and the last review changed nothing.

10. If a draft PR exists, mark it ready for review. Otherwise, resolve each ticket the way the issue tracker closes work, and report the integration branch.

11. Clean up all **implementer subagent** worktrees, and stop the local services (`localstart/startserver.sh stop --siblings` in each tested service's `testcase/`).
