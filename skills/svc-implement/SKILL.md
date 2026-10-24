---
name: svc-implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

If the user passes a ticket reference, fetch it from the issue tracker and state its title before starting. If the reference is ambiguous, ask.

Note the current `HEAD` before you start: it is the fixed point for every review below.

1. **Implement.** Run typechecking (`go build ./... && go vet ./...`) regularly, and the existing test suite once at the end. Commit your work to the current branch.

2. **Test.** Call the Skill tool with "svc-local-test-flow" to start the service locally and test it end to end: it generates cases from the committed code, stops for the user to confirm them, prepares the local environment, and runs the cases with evidence. Fix the failures it reports, commit the fixes, and call "svc-local-test-flow" again (it picks the 同步 route for changed code).
   Done when every case passes, or the rest are blocked on the user.

3. **Review.** Call the Skill tool with "svc-code-review", fixed point the `HEAD` you noted.
   Done when every finding is either applied or explained to the user as left as is.

4. **Loop.** If step 3 changed any code, commit it and go back to step 2. Otherwise you are finished: the last test round passed and the last review changed nothing.
