# EXAMPLE 1 - Task Description: Wash the fork. 
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Wash the Fork. (Skills Required: GoToObject, PickupObject, PutObject, SwitchOn, SwitchOff)
# We can perform SubTask 1 

# CODE
def wash_fork():
    # 0: SubTask 1: Wash the Fork
    # 1: Go to the Fork.
    GoToObject('Fork')
    # 2: Pick up the Fork.
    PickupObject('Fork')
    # 3: Go to the Sink.
    GoToObject('Sink')
    # 4: Put the Fork inside the Sink
    PutObject('Fork', 'Sink')
    # 5: Switch on the Faucet to clean the Fork
    SwitchOn('Faucet')
    # 6: Wait for a while to let the Fork clean.
    time.sleep(5)
    # 7: Switch off the Faucet
    SwitchOff('Faucet')
# Perform SubTask 1
task1_thread = threading.Thread(target=wash_fork)
# Start executing SubTask 1 
task1_thread.start()
# Task wash the fork is done

# TASK ALLOCATION
robots = [{'name': 'robot1', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'SliceObject', 'SwitchOn', 'SwitchOff', 'DropHandObject', 'ThrowObject', 'PushObject', 'PullObject'],'mass': 2}, {'name': 'robot2', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'SliceObject', 'PickupObject', 'PutObject', 'SwitchOn', 'SwitchOff', 'DropHandObject', 'ThrowObject', 'PushObject', 'PullObject'],'mass': 2}]
# SOLUTION
# All the robots DONOT share the same set and number (no_skills) of skills & all objects have different masses. In this case where all robots have different sets of skills and objects have different mass - Focus on Task Allocation based on Robot Skills alone. 
# Analyze the skills required for each subtask and the skills each robot possesses. In this scenario, we have one main subtasks: 'Wash the Fork'.
# For the 'Wash the Fork' subtask, it requires 'GoToObject', 'PickupObject', 'PutObject', 'SwitchOn', and 'SwitchOff' skills. In this case, Robot 2 has all these skills.  
# No teams are required since SubTasks can be performed with individual robots as explained above. The 'Wash the Fork' subtask is assigned Robot 2. 

# Code Solution 
def wash_fork(robot_list):
    # robot_list = [robot1]
    # 0: SubTask 2: Wash the Fork
    # 1: Go to the Fork using robot1.
    GoToObject(robot_list[0],'Fork')
    # 2: Pick up the Fork using robot1.
    PickupObject(robot_list[0],'Fork')
    # 3: Go to the Sink using robot1.
    GoToObject(robot_list[0],'Sink')
    # 4: Put the Fork inside the Sink using robot1
    PutObject(robot_list[0],'Fork', 'Sink')
    # 5: Switch on the Faucet to clean the Fork using robot1
    SwitchOn(robot_list[0],'Faucet')
    # 6: Wait for a while to let the Fork clean using robot1.
    time.sleep(5)
    # 7: Switch off the Faucet using robot1
    SwitchOff(robot_list[0],'Faucet')
# Perform SubTask 1 with robot2
wash_fork([robots[1]])
# Task wash the fork is done


# EXAMPLE 2 - Task Description: Put tomato in fridge 
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Put Tomato in Fridge. (Skills Required: GoToObject, PickupObject, OpenObject, PutObject, CloseObject)
# We can perform SubTask 1.

# CODE
def put_tomato_in_fridge():
    # 0: SubTask 1: Put Tomato in Fridge
    # 1: Go to the Tomato.
    GoToObject('Tomato')
    # 2: Pick up the Tomato.
    PickupObject('Tomato')
    # 3: Go to the Fridge.
    GoToObject('Fridge')
    # 4: Open the Fridge.
    OpenObject('Fridge')
    # 5: Put the Tomato in the Fridge.
    PutObject('Tomato', 'Fridge')
    # 6: Close the Fridge.
    CloseObject('Fridge')
# Perform SubTask 1
task1_thread = threading.Thread(target=put_tomato_in_fridge)
# Start executing SubTask 1
task1_thread.start()
# Task Put tomato in fridge is done

# TASK ALLOCATION
robots = [{'name': 'robot1', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'SliceObject', 'PickupObject', 'PutObject', 'SwitchOn', 'SwitchOff', 'DropHandObject', 'ThrowObject', 'PushObject', 'PullObject'],'mass': 4}, {'name': 'robot2', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'SliceObject', 'PickupObject', 'PutObject', 'SwitchOn', 'SwitchOff', 'DropHandObject', 'ThrowObject', 'PushObject', 'PullObject'],'mass': 1}, {'name': 'robot3', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'SliceObject', 'PickupObject', 'PutObject', 'SwitchOn', 'SwitchOff', 'DropHandObject', 'ThrowObject', 'PushObject', 'PullObject'],'mass': 2}]
# SOLUTION
# All the robots share the same set and number of skills (no_skills) & all objects DONOT have same mass. In this case where all objects have different mass, and robots have same sets of skills- Focus on Task Allocation based on Mass alone. 
# Analyze the mass required for each object being PickedUp by the 'PickupObject' skill, and the mass capacity each robot possesses. In this scenario, we have one main subtasks: 'Put Tomato in Fridge.'.
# For the 'Put Tomato in Fridge.' subtask, mass of the Tomato is 4. Hence the subtask can be performed by any robot with mass capacity greater than or equal to 4. In this case, Robots 1 has a mass capacity = 4.
# No teams are required since SubTasks can be performed with individual robots as explained above. The 'Put Tomato in Fridge.' subtask is assigned to Robot 1. 

# Code Solution 
def put_tomato_in_fridge(robot_list):
    # robot_list = [robot1]
    # 0: SubTask 1: Put Tomato in Fridge
    # 1: Go to the Tomato using robot1.
    GoToObject(robot_list,'Tomato')
    # 2: Pick up the Tomato using robot1.
    PickupObject(robot_list,'Tomato')
    # 3: Go to the Fridge using robot1.
    GoToObject(robot_list,'Fridge')
    # 4: Open the Fridge using robot1.
    OpenObject(robot_list,'Fridge')
    # 5: Put the Tomato in the Fridge using robot1.
    PutObject(robot_list,'Tomato', 'Fridge')
    # 6: Close the Fridge using robot1.
    CloseObject(robot_list,'Fridge')
# Perform SubTask 1 
put_tomato_in_fridge([robots[0]])

# Task Put tomato in fridge is done


# EXAMPLE 3 - Task Description: Slice the Potato 
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Slice the Potato. (Skills Required: GoToObject, PickupObject, SliceObject, PutObject)
# We can execute SubTask 1 first.

# CODE
def slice_potato():
    # 0: SubTask 1: Slice the Potato
    # 1: Go to the Knife.
    GoToObject('Knife')
    # 2: Pick up the Knife.
    PickupObject('Knife')
    # 3: Go to the Potato.
    GoToObject('Potato')
    # 4: Slice the Potato.
    SliceObject('Potato')
    # 5: Go to the countertop.
    GoToObject('CounterTop')
    # 6: Put the Knife back on the CounterTop.
    PutObject('Knife', 'CounterTop')
# Execute SubTask 1
slice_potato()
# Task fry sliced potato is done


# TASK ALLOCATION
robots = [{'name': 'robot1', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'SliceObject'],'mass': 2}, {'name': 'robot2', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'SwitchOn', 'SwitchOff', 'DropHandObject', 'ThrowObject', 'PushObject', 'PullObject'],'mass': 2}, {'name': 'robot3', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'PickupObject', 'PutObject', 'DropHandObject'],'mass': 2}]
# SOLUTION
# All the robots DONOT share the same set and number of skills (no_skills) & all objects have different masses. In this case where all robots have different sets of skills and objects have different mass - Focus on Task Allocation based on Robot Skills alone. 
# Analyze the skills required for each subtask and the skills each robot possesses. In this scenario, we have one main subtasks: 'Slice the Potato'.
# For the 'Slice the Potato' subtask, it can be performed by any robot with 'GoToObject', 'PickupObject', 'SliceObject' and 'PutObject' skills. However, no individual robot has all these skills. This is a skill gap that needs to be addressed. Form a team of robots. The skills of the team must be 'GoToObject', 'PickupObject', 'SliceObject' and 'PutObject' skills. Team of Robots 1 and 3 have all the skills required where robot 1 has the 'SliceObject' skill and Robot 3 has the 'GoToObject', 'PickupObject', and 'PutObject' skills.
# Teams are required since SubTasks can't be performed with individual robots as explained above. The 'Slice the Potato' subtask is assigned to team of Robots 1 and 3. 

# Code Solution
def slice_potato(robot_list):
    # robot_list = [robot1,robot3]
    # 0: SubTask 1: Slice the Potato
    # 1: Go to the Knife  using robot3.
    GoToObject(robot_list[1],'Knife')
    # 2: Pick up the Knife using robot3.
    PickupObject(robot_list[1],'Knife')
    # 3: Go to the Potato using robot3.
    GoToObject(robot_list[1],'Potato')
    # 4: Slice the Potato using robot1.
    SliceObject(robot_list[0],'Potato')
    # 5: Go to the countertop using robot3.
    GoToObject(robot_list[1],'CounterTop')
    # 6: Put the Knife back on the CounterTop using robot3.
    PutObject(robot_list[1],'Knife', 'CounterTop')
# Execute SubTask 1
slice_potato([robots[0],robots[2]])
# Task fry sliced potato is done


# EXAMPLE 4 - Task Description: Throw the fork in the trash
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Pick up the Fork. (Skills Required: GoToObject, PickupObject)
# SubTask 2: Throw the Fork in the Trash. (Skills Required: GoToObject, ThrowObject)
# We can execute SubTask 1 first and then SubTask 2.

# CODE
def pick_up_fork():
    # 0: SubTask 1: Pick up the Fork
    # 1: Go to the Fork.
    GoToObject('Fork')
    # 2: Pick up the Fork.
    PickupObject('Fork')

def throw_fork_in_trash():
    # 0: SubTask 2: Throw the Fork in the Trash
    # 1: Go to the GarbageCan.
    GoToObject('GarbageCan')
    # 2: Throw the Fork in the GarbageCan.
    ThrowObject('Fork', 'GarbageCan')

# Execute SubTask 1
pick_up_fork()

# Execute SubTask 2
throw_fork_in_trash()

# Task throw the fork in the trash is done


# TASK ALLOCATION
robots = [{'name': 'robot1', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'SliceObject', 'PickupObject', 'PutObject', 'SwitchOn', 'SwitchOff', 'DropHandObject', 'ThrowObject', 'PushObject', 'PullObject'],'mass': 3}, {'name': 'robot2', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'SliceObject', 'PickupObject', 'PutObject', 'SwitchOn', 'SwitchOff', 'DropHandObject', 'ThrowObject', 'PushObject', 'PullObject'],'mass': 2}, {'name': 'robot3', 'skills': ['GoToObject', 'OpenObject', 'CloseObject', 'BreakObject', 'SliceObject', 'PickupObject', 'PutObject', 'SwitchOn', 'SwitchOff', 'DropHandObject', 'ThrowObject', 'PushObject', 'PullObject'],'mass': 2}]
# SOLUTION
# All the robots share the same set and number of skills (no_skills) & all objects DONOT have same mass. In this case where all objects have different mass, and robots have same sets of skills- Focus on Task Allocation based on Mass alone. 
# Analyze the mass required for each object being PickedUp by the 'PickupObject' skill, and the mass capacity each robot possesses. In this scenario, we have two main subtasks: 'Pick up the Fork' and 'Throw the Fork in the Trash'.
# For the 'Pick up the Fork' subtask, mass of the Fork is 5. Hence the subtask can be performed by any robot with mass capacity greater than or equal to 5. However, no individual robot has mass capacity of 5. This is a mass gap that needs to be addressed. Form a team of robots. The combined mass capacity of the team must be greater than or equal to 5. Team of Robots 1 and 2 have the mass capacity required where robot1 has mass capacity of 3 and where robot2 has mass capacity of 2 , this gives a combined mass capacity of 5.
# For the 'Throw the Fork in the Trash' subtask, mass of the Fork is 5. Hence the subtask can be performed by any robot with mass capacity greater than or equal to 5. However, no individual robot has mass capacity of 5. This is a mass gap that needs to be addressed. Form a team of robots. The combined mass capacity of the team must be greater than or equal to 5. Team of Robots 1 and 3 have the mass capacity required where robot1 has mass capacity of 3 and where robot3 has mass capacity of 2 , this gives a combined mass capacity of 5.
# Teams are required since SubTasks can't be performed with individual robots as explained above. The 'Pick up the Fork' subtask is assigned to team of Robots 1 and 2. The 'Throw the Fork in the Trash' subtask is assigned to team of Robots 1 and 3. 

# CODE Solution
def pick_up_fork(robot_list):
    # robot_list = [robot1,robot2]
    # 0: SubTask 1: Pick up the Fork
    # 1: Go to the Fork using robot1 and robot2 togethor.
    GoToObject(robot_list,'Fork')
    # 2: Pick up the Fork using robot1 and robot2 togethor.
    PickupObject(robot_list,'Fork')

def throw_fork_in_trash():
    # robot_list = [robot1,robot3]
    # 0: SubTask 2: Throw the Fork in the Trash
    # 1: Go to the GarbageCan using robot1 and robot3 togethor.
    GoToObject(robot_list,'GarbageCan')
    # 2: Throw the Fork in the GarbageCan using robot1 and robot3 togethor.
    ThrowObject(robot_list,'Fork', 'GarbageCan')

# Execute SubTask 1
pick_up_fork([robots[0],robots[1]])

# Execute SubTask 2
throw_fork_in_trash([robots[0],robots[2]])

# Task throw the fork in the trash is done

# EXAMPLE 5 - Task Description: Pick up the bread and use the microwave to heat an object.
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Pick up the bread and heat an object (referring to the bread). (Skills Required: GoToObject, PickupObject, OpenObject, PutObject, CloseObject, SwitchOn, SwitchOff)
# Note: "an object" in context refers to the bread
# We can execute SubTask 1

# CODE
def pickup_bread_and_heat_object():
    # 0: SubTask 1: Pick up the bread and heat an object
    # 1: Go to the Bread.
    GoToObject('Bread')
    # 2: Pick up the Bread.
    PickupObject('Bread')
    # 3: Go to the Microwave.
    GoToObject('Microwave')
    # 4: Open the Microwave.
    OpenObject('Microwave')
    # 5: Put the Bread inside the Microwave
    PutObject('Bread', 'Microwave')
    # 6: Close the Microwave
    CloseObject('Microwave')
    # 7: Switch on Microwave
    SwitchOn('Microwave')
    # 8: Wait for a while to heat the bread.
    time.sleep(5)
    # 9: Switch off Microwave
    SwitchOff('Microwave')

# Execute SubTask 1
pickup_bread_and_heat_object()

# Task pick up the bread and heat an object is done

# TASK ALLOCATION
robots = [{'name': 'robot1', 'skills': ['GoToObject', 'PickupObject', 'PutObject', 'OpenObject', 'CloseObject', 'SwitchOn', 'SwitchOff'], 'mass': 3}]

# SOLUTION
# Robot 1 has all required skills: GoToObject, PickupObject, OpenObject, PutObject, CloseObject, SwitchOn, SwitchOff. Assign Robot 1 to perform the task.

# CODE Solution
def pickup_bread_and_heat_object(robot_list):
    # robot_list = [robot1]
    # 0: SubTask 1: Pick up the bread and heat an object (the bread)
    # 1: Go to the Bread using robot1.
    GoToObject(robot_list[0], 'Bread')
    # 2: Pick up the Bread using robot1.
    PickupObject(robot_list[0], 'Bread')
    # 3: Go to the Microwave using robot1.
    GoToObject(robot_list[0], 'Microwave')
    # 4: Open the Microwave using robot1.
    OpenObject(robot_list[0], 'Microwave')
    # 5: Put the Bread inside the Microwave using robot1
    PutObject(robot_list[0], 'Bread', 'Microwave')
    # 6: Close the Microwave using robot1
    CloseObject(robot_list[0], 'Microwave')
    # 7: Switch on Microwave using robot1
    SwitchOn(robot_list[0], 'Microwave')
    # 8: Wait for a while to heat the bread.
    time.sleep(5)
    # 9: Switch off Microwave using robot1
    SwitchOff(robot_list[0], 'Microwave')

# Execute SubTask 1
pickup_bread_and_heat_object([robots[0]])

# Task pick up the bread and heat an object is done

# EXAMPLE 6 - Task Description: Pickup the apple and wash an object.
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Pickup the apple and wash an object (referring to the apple). (Skills Required: GoToObject, PickupObject, PutObject, SwitchOn, SwitchOff)
# Note: "an object" in context refers to the apple
# We can execute SubTask 1

# CODE
def pickup_apple_and_wash_object():
    # 0: SubTask 1: Pickup the apple and wash an object
    # 1: Go to the Apple.
    GoToObject('Apple')
    # 2: Pick up the Apple.
    PickupObject('Apple')
    # 3: Go to the Sink.
    GoToObject('Sink')
    # 4: Put the Apple inside the Sink
    PutObject('Apple', 'Sink')
    # 5: Switch on the Faucet to clean the Apple
    SwitchOn('Faucet')
    # 6: Wait for a while to let the Apple clean.
    time.sleep(5)
    # 7: Switch off the Faucet
    SwitchOff('Faucet')

# Execute SubTask 1
pickup_apple_and_wash_object()

# Task pickup the apple and wash an object is done

# TASK ALLOCATION
robots = [{'name': 'robot1', 'skills': ['GoToObject', 'PickupObject', 'PutObject', 'SwitchOn', 'SwitchOff'], 'mass': 2}]

# SOLUTION
# Robot 1 has all required skills: GoToObject, PickupObject, PutObject, SwitchOn, SwitchOff. Assign Robot 1 to perform the task.

# CODE Solution
def pickup_apple_and_wash_object(robot_list):
    # robot_list = [robot1]
    # 0: SubTask 1: Pickup the apple and wash an object (the apple)
    # 1: Go to the Apple using robot1.
    GoToObject(robot_list[0], 'Apple')
    # 2: Pick up the Apple using robot1.
    PickupObject(robot_list[0], 'Apple')
    # 3: Go to the Sink using robot1.
    GoToObject(robot_list[0], 'Sink')
    # 4: Put the Apple inside the Sink using robot1
    PutObject(robot_list[0], 'Apple', 'Sink')
    # 5: Switch on the Faucet to clean the Apple using robot1
    SwitchOn(robot_list[0], 'Faucet')
    # 6: Wait for a while to let the Apple clean.
    time.sleep(5)
    # 7: Switch off the Faucet using robot1
    SwitchOff(robot_list[0], 'Faucet')

# Execute SubTask 1
pickup_apple_and_wash_object([robots[0]])

# Task pickup the apple and wash an object is done

# EXAMPLE 7 - Task Description: Clean the table.
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Clean the table by removing all objects from it. (Skills Required: GoToObject, PickupObject, PutObject)
# Note: "clean the table" means clear the table surface (CounterTop) by moving objects elsewhere
# Strategy: Identify what objects are on CounterTop, then move each to another location
# We can execute SubTask 1

# CODE
def clean_table():
    # 0: SubTask 1: Clean the table (remove all objects from CounterTop)
    # Note: In this scenario, CounterTop currently has Bowl, Mug, and Plate on it
    # Strategy: Remove each object one by one
    # 1: Go to the Bowl on CounterTop.
    GoToObject('Bowl')
    # 2: Pick up the Bowl.
    PickupObject('Bowl')
    # 3: Go to the Sink.
    GoToObject('Sink')
    # 4: Put the Bowl in the Sink
    PutObject('Bowl', 'Sink')
    # 5: Go to the Mug on CounterTop.
    GoToObject('Mug')
    # 6: Pick up the Mug.
    PickupObject('Mug')
    # 7: Go to the Sink.
    GoToObject('Sink')
    # 8: Put the Mug in the Sink
    PutObject('Mug', 'Sink')
    # 9: Go to the Plate on CounterTop.
    GoToObject('Plate')
    # 10: Pick up the Plate.
    PickupObject('Plate')
    # 11: Go to the Sink.
    GoToObject('Sink')
    # 12: Put the Plate in the Sink
    PutObject('Plate', 'Sink')
    # Now CounterTop is clear

# Execute SubTask 1
clean_table()

# Task clean the table is done

# TASK ALLOCATION
robots = [{'name': 'robot1', 'skills': ['GoToObject', 'PickupObject', 'PutObject'], 'mass': 3}]

# SOLUTION
# Robot 1 has all required skills: GoToObject, PickupObject, PutObject. Assign Robot 1 to perform the task of removing objects from the table.

# CODE Solution
def clean_table(robot_list):
    # robot_list = [robot1]
    # 0: SubTask 1: Clean the table (remove all objects from CounterTop)
    # Note: In this scenario, CounterTop currently has Bowl, Mug, and Plate on it
    # Strategy: Check what objects are on CounterTop, then remove each one
    # 1: Go to the Bowl on CounterTop using robot1.
    GoToObject(robot_list[0], 'Bowl')
    # 2: Pick up the Bowl using robot1.
    PickupObject(robot_list[0], 'Bowl')
    # 3: Go to the Sink using robot1.
    GoToObject(robot_list[0], 'Sink')
    # 4: Put the Bowl in the Sink using robot1
    PutObject(robot_list[0], 'Bowl', 'Sink')
    # 5: Go to the Mug on CounterTop using robot1.
    GoToObject(robot_list[0], 'Mug')
    # 6: Pick up the Mug using robot1.
    PickupObject(robot_list[0], 'Mug')
    # 7: Go to the Sink using robot1.
    GoToObject(robot_list[0], 'Sink')
    # 8: Put the Mug in the Sink using robot1
    PutObject(robot_list[0], 'Mug', 'Sink')
    # 9: Go to the Plate on CounterTop using robot1.
    GoToObject(robot_list[0], 'Plate')
    # 10: Pick up the Plate using robot1.
    PickupObject(robot_list[0], 'Plate')
    # 11: Go to the Sink using robot1.
    GoToObject(robot_list[0], 'Sink')
    # 12: Put the Plate in the Sink using robot1
    PutObject(robot_list[0], 'Plate', 'Sink')
    # Now CounterTop is clear

# Execute SubTask 1
clean_table([robots[0]])

# Task clean the table is done

# EXAMPLE 8 - Task Description: Switch on the stove and heat an object.
# GENERAL TASK DECOMPOSITION
# Independent subtasks:
# SubTask 1: Switch on the stove and heat an object using a pan. (Skills Required: GoToObject, SwitchOn, PickupObject, PutObject, SwitchOff)
# Note: Proper stove usage requires: 1) Place Pan on StoveBurner first, 2) Put food in Pan, 3) Switch off when done
# We can execute SubTask 1

# CODE
def switch_on_stove_and_heat_object():
    # 0: SubTask 1: Switch on the stove and heat an object (tomato)
    # 1: Go to the StoveKnob.
    GoToObject('StoveKnob')
    # 2: Switch on the StoveKnob to turn on the stove.
    SwitchOn('StoveKnob')
    # 3: Go to the Pan.
    GoToObject('Pan')
    # 4: Pick up the Pan.
    PickupObject('Pan')
    # 5: Go to the StoveBurner.
    GoToObject('StoveBurner')
    # 6: Put the Pan on the StoveBurner.
    PutObject('Pan', 'StoveBurner')
    # 7: Go to the Tomato.
    GoToObject('Tomato')
    # 8: Pick up the Tomato.
    PickupObject('Tomato')
    # 9: Go back to the StoveBurner.
    GoToObject('StoveBurner')
    # 10: Put the Tomato in the Pan.
    PutObject('Tomato', 'Pan')
    # 11: Wait for the food to cook.
    time.sleep(10)
    # 12: Switch off the StoveKnob.
    SwitchOff('StoveKnob')

# Execute SubTask 1
switch_on_stove_and_heat_object()

# Task switch on the stove and heat an object is done

# TASK ALLOCATION
robots = [{'name': 'robot1', 'skills': ['GoToObject', 'PickupObject', 'PutObject', 'SwitchOn', 'SwitchOff'], 'mass': 3}]

# SOLUTION
# Robot 1 has all required skills: GoToObject, PickupObject, PutObject, SwitchOn, SwitchOff. Assign Robot 1 to perform the task.

# CODE Solution
def switch_on_stove_and_heat_object(robot_list):
    # robot_list = [robot1]
    # 0: SubTask 1: Switch on the stove and heat an object (tomato)
    # Note: Proper stove usage sequence - Pan first, then food in Pan
    # 1: Go to the StoveKnob using robot1.
    GoToObject(robot_list[0], 'StoveKnob')
    # 2: Switch on the StoveKnob to turn on the stove using robot1.
    SwitchOn(robot_list[0], 'StoveKnob')
    # 3: Go to the Pan using robot1.
    GoToObject(robot_list[0], 'Pan')
    # 4: Pick up the Pan using robot1.
    PickupObject(robot_list[0], 'Pan')
    # 5: Go to the StoveBurner using robot1.
    GoToObject(robot_list[0], 'StoveBurner')
    # 6: Put the Pan on the StoveBurner using robot1.
    PutObject(robot_list[0], 'Pan', 'StoveBurner')
    # 7: Go to the Tomato using robot1.
    GoToObject(robot_list[0], 'Tomato')
    # 8: Pick up the Tomato using robot1.
    PickupObject(robot_list[0], 'Tomato')
    # 9: Go back to the StoveBurner using robot1.
    GoToObject(robot_list[0], 'StoveBurner')
    # 10: Put the Tomato in the Pan using robot1.
    PutObject(robot_list[0], 'Tomato', 'Pan')
    # 11: Wait for the food to cook.
    time.sleep(10)
    # 12: Switch off the StoveKnob using robot1.
    SwitchOff(robot_list[0], 'StoveKnob')

# Execute SubTask 1
switch_on_stove_and_heat_object([robots[0]])

# Task switch on the stove and heat an object is done
# Task pickup the apple and wash an object is done