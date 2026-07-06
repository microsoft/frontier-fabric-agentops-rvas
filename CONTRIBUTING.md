# Contributing to the Frontier Fabric AgentOps RVAS

Thanks for your interest in improving this RVAS! This repo is an open teaching asset — the more
real-world the challenges, hints, and coach guides are, the better the experience for the next
customer team that runs it. Contributions of all sizes are welcome, from fixing a typo to authoring a
brand-new challenge.

## Ways to contribute

| Contribution | Where it lives |
|---|---|
| Improve or clarify an attendee challenge | `challenges/challenge-0X-*.md` |
| Sharpen a coach guide (pitfalls, talking points, reference path) | `coach/challenge-0X-guide.md` |
| Fix or extend the reference implementation | `resources/**` |
| Update architecture, prerequisites, or FAQ | `docs/**` |
| Add a brand-new challenge or stretch goal | `challenges/` **and** `coach/` (always add both) |
| Report a bug or unclear instruction | GitHub Issues |

## Golden rule: challenges and coach guides travel together

Every attendee-facing challenge in `challenges/` has a matching instructor guide in `coach/`. If you
change one, update the other in the same pull request so they never drift:

- A new task in a challenge needs a matching checkpoint + reference path in the guide.
- A renamed file needs its prev/next nav links and the coach cross-link updated.

## House style

**Attendee challenges** (`challenges/`) describe **what** to accomplish, not **how**:

1. A short "mission log" blockquote story hook at the top.
2. `## Objectives` and `## Prerequisites`.
3. `## Your mission` — numbered task groups describing the goal, not click-by-click steps.
4. `## Success criteria` — a verifiable checklist.
5. `## Hints` — progressive disclosure inside `<details><summary>…</summary></details>` blocks.
6. `## Resources` — links into `resources/` and `docs/`.
7. A footer with `⬅️ Previous` / `➡️ Next` navigation links.

**Coach guides** (`coach/`) give instructors the answers:

1. A snapshot table (duration, difficulty, dependencies, business question).
2. Coaching objectives and a concrete reference path (exact commands/paths).
3. Checkpoint verification, a common-pitfalls table, talking points, and an "if they finish early" note.

Keep the three business questions — **reliability, cost, performance** — threaded through new content.

## Making changes

1. Fork the repo and create a topic branch: `git checkout -b improve-challenge-04`.
2. Make your changes. Keep relative Markdown links valid (challenge nav, coach cross-links, `resources/` and `docs/` references).
3. Open a pull request with a clear description of the change and which challenge(s)/guide(s) it affects.
4. For substantive changes, please open an Issue first so we can align on direction.

## Reporting issues

Use GitHub Issues for bug reports, unclear instructions, broken links, or environment/setup problems
encountered during a run. Please include the challenge number, your environment (Azure region, Fabric
capacity SKU), and what you expected vs. what happened.

## Contributor License Agreement

This project welcomes contributions and suggestions. Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit <https://cla.opensource.microsoft.com>.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide a
CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

## Code of Conduct

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/)
or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of
Microsoft trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or
imply Microsoft sponsorship. Any use of third-party trademarks or logos is subject to those
third-party's policies.
