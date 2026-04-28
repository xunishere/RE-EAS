# SINGLE ROBOT OUTPUT CONTRACT
#
# You must follow every rule below when generating the final plan.
#
# 1. Output only valid Python code.
# 2. Do not use markdown code fences such as ```python.
# 3. Do not output explanations, reasoning, summaries, or natural-language prose.
# 4. Use exactly one robot variable named `robot`.
# 5. Every action call must pass `robot` as the first argument.
# 6. Never use `robots`, `robot_list`, `team`, `allocation`, or any multi-robot structure.
# 7. Only call the following actions:
#    GoToObject
#    PickupObject
#    PutObject
#    OpenObject
#    CloseObject
#    SwitchOn
#    SwitchOff
#    SliceObject
#    BreakObject
#    ThrowObject
# 8. You may use `time.sleep(...)` when the task requires waiting.
# 9. Only use object names that appear in the provided `objects` list.
# 10. Do not invent objects such as `Table`, `Desk`, or any name not present in `objects`.
# 11. Prefer small helper functions followed by direct execution calls.
# 12. Preserve execution order explicitly in code.
# 13. Do not use `threading.Thread`, `.start()`, or `.join()`.
# 14. Do not emit import statements because the runtime already provides the required imports.
# 15. The final answer must be directly writable to `code_plan.py` and executable after connector injection.
# 16. If the instruction says "put it aside", "throw it aside", or "move it away" without naming a receptacle,
#     prefer `ThrowObject` instead of `PutObject`.
# 17. Do not map "put it aside" to `PutObject(..., 'CounterTop')`, `PutObject(..., 'Table')`, or any other receptacle
#     unless the task explicitly names that receptacle.
# 18. When washing an object under a faucet or at a sink, prefer `SinkBasin` as the receptacle target rather than `Sink`.
# 19. When heating bread in a microwave, do not place whole `Bread` directly into the microwave. First pick up a knife,
#     call `SliceObject(robot, 'Bread')`, then put down the knife, then pick up `BreadSliced`, and only then place
#     `BreadSliced` into the microwave.
# 20. If the robot is holding a knife after slicing bread, it must put down the knife before calling `PickupObject(robot, 'BreadSliced')`.
#
# REQUIRED STYLE
#
# Example shape:
#
# def task_step():
#     GoToObject(robot, 'Tomato')
#     PickupObject(robot, 'Tomato')
#     GoToObject(robot, 'Fridge')
#     OpenObject(robot, 'Fridge')
#     PutObject(robot, 'Tomato', 'Fridge')
#     CloseObject(robot, 'Fridge')
#
# task_step()
