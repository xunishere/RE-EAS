# SINGLE ROBOT CODE GENERATION EXAMPLES
# The examples below teach the model how to translate a decomposed task plan
# into executable Python code for exactly one robot in AI2-THOR.
# The runtime already provides:
# - actions imported from `skills`
# - `time`
# - `threading`
# - `objects`
# - `robot`
#
# Rules demonstrated by the examples:
# 1. Always use the single available robot variable: `robot`.
# 2. Every action call must pass `robot` as the first argument.
# 3. Do not create robot teams, `robots[...]`, or `robot_list`.
# 4. Output only Python code.
# 5. Only use object names that exist in `objects`.


# EXAMPLE 1 - Task Description: Put the tomato in the fridge.
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Put the Tomato in the Fridge. (Skills Required: GoToObject, PickupObject, OpenObject, PutObject, CloseObject)
# We can execute SubTask 1 directly.

# CODE
def put_tomato_in_fridge():
    # 0: SubTask 1: Put the Tomato in the Fridge
    # 1: Go to the Tomato using the single robot.
    GoToObject(robot, 'Tomato')
    # 2: Pick up the Tomato using the single robot.
    PickupObject(robot, 'Tomato')
    # 3: Go to the Fridge using the single robot.
    GoToObject(robot, 'Fridge')
    # 4: Open the Fridge using the single robot.
    OpenObject(robot, 'Fridge')
    # 5: Put the Tomato in the Fridge using the single robot.
    PutObject(robot, 'Tomato', 'Fridge')
    # 6: Close the Fridge using the single robot.
    CloseObject(robot, 'Fridge')


put_tomato_in_fridge()


# EXAMPLE 2 - Task Description: Slice the potato and leave the knife on the countertop.
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Slice the Potato. (Skills Required: GoToObject, PickupObject, SliceObject, PutObject)
# We can execute SubTask 1 directly.

# CODE
def slice_potato():
    # 0: SubTask 1: Slice the Potato
    # 1: Go to the Knife using the single robot.
    GoToObject(robot, 'Knife')
    # 2: Pick up the Knife using the single robot.
    PickupObject(robot, 'Knife')
    # 3: Go to the Potato using the single robot.
    GoToObject(robot, 'Potato')
    # 4: Slice the Potato using the single robot.
    SliceObject(robot, 'Potato')
    # 5: Go to the CounterTop using the single robot.
    GoToObject(robot, 'CounterTop')
    # 6: Put the Knife on the CounterTop using the single robot.
    PutObject(robot, 'Knife', 'CounterTop')


slice_potato()


# EXAMPLE 3 - Task Description: Wash the fork in the sink.
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Wash the Fork in the Sink. (Skills Required: GoToObject, PickupObject, PutObject, SwitchOn, SwitchOff)
# We can execute SubTask 1 directly.

# CODE
def wash_fork():
    # 0: SubTask 1: Wash the Fork in the Sink
    # 1: Go to the Fork using the single robot.
    GoToObject(robot, 'Fork')
    # 2: Pick up the Fork using the single robot.
    PickupObject(robot, 'Fork')
    # 3: Go to the Sink using the single robot.
    GoToObject(robot, 'Sink')
    # 4: Put the Fork in the Sink using the single robot.
    PutObject(robot, 'Fork', 'Sink')
    # 5: Turn on the Faucet using the single robot.
    SwitchOn(robot, 'Faucet')
    # 6: Wait while the Fork is being cleaned.
    time.sleep(5)
    # 7: Turn off the Faucet using the single robot.
    SwitchOff(robot, 'Faucet')


wash_fork()


# EXAMPLE 4 - Task Description: Pick up the bowl and put it aside.
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Pick up the Bowl. (Skills Required: GoToObject, PickupObject)
# SubTask 2: Throw the Bowl aside. (Skills Required: ThrowObject)
# We execute SubTask 1 and then SubTask 2.

# CODE
def pick_up_bowl_and_put_aside():
    # 0: SubTask 1: Pick up the Bowl
    # 1: Go to the Bowl using the single robot.
    GoToObject(robot, 'Bowl')
    # 2: Pick up the Bowl using the single robot.
    PickupObject(robot, 'Bowl')
    # 3: Throw the Bowl aside using the single robot.
    ThrowObject(robot, 'Bowl')


pick_up_bowl_and_put_aside()
