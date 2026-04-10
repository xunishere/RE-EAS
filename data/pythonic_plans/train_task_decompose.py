# Task Description: Put an Egg in the Fridge, and place a pot containing Apple slices into the refrigerator.

# GENERAL TASK DECOMPOSITION 
# Decompose and parallelize subtasks where ever possible
# Independent subtasks:
# SubTask 1: Put an Egg in the Fridge. (Skills Required: GoToObject, PickupObject, OpenObject, PutObject, CloseObject)
# SubTask 2: Prepare Apple Slices. (Skills Required: GoToObject, PickupObject, SliceObject, PutObject)
# SubTask 3: Place the Pot with Apple Slices in the Fridge. (Skills Required: GoToObject, PickupObject, PutObject, OpenObject, CloseObject)
# We can parallelize SubTask 1 and SubTask 2 because they don't depend on each other.

# CODE
def put_egg_in_fridge():
    # 0: SubTask 1: Put an Egg in the Fridge
    # 1: Go to the Egg.
    GoToObject('Egg')
    # 2: Pick up the Egg.
    PickupObject('Egg')
    # 3: go to the Fridge.
    GoToObject('Fridge')
    # 4: Open the Fridge.
    OpenObject('Fridge')
    # 5: place the Egg inside the Fridge
    PutObject('Egg', 'Fridge')
    # 6: Close the Fridge.
    CloseObject('Fridge')

def prepare_apple_slices():
    # 0: SubTask 2: Prepare Apple Slices
    # 1: Go to the Knife.
    GoToObject('Knife')
    # 2: Pick up the Knife.
    PickupObject('Knife')
    # 3: Go to the Apple.
    GoToObject('Apple')
    # 4: Cut the Apple into slices.
    SliceObject('Apple')
    # 5: Go to the diningtable.
    GoToObject('DiningTable')
    # 6: Put the Knife on the diningtable.
    PutObject('Knife', 'DiningTable')

def place_pot_with_apple_slices():
    # 0: SubTask 3: Place the Pot with Apple Slices in the Fridge
    # 1: Go to the Apple slice.
    GoToObject('Apple')
    # 2: Pick up a slice of Apple.
    PickupObject('Apple')
    # 3: Go to the pot.
    GoToObject('Pot')
    # 4: Place the Apple slice in the pot.
    PutObject('Apple', 'Pot')
    # 5: Pick up the pot.
    PickupObject('Pot')
    # 6: Go to the refrigerator.
    GoToObject('Fridge')
    # 7: Open the Fridge, 
    OpenObject('Fridge')
    # 8: Put the pot in the refrigerator.
    PutObject('Pot', 'Fridge')
    # 9: Close the Fridge.
    CloseObject('Fridge')

# Parallelize SubTask 1 and SubTask 2
task1_thread = threading.Thread(target=put_egg_in_fridge)
task2_thread = threading.Thread(target=prepare_apple_slices)

# Start executing SubTask 1 and SubTask 2 in parallel
task1_thread.start()
task2_thread.start()

# Wait for both SubTask 1 and SubTask 2 to finish
task1_thread.join()
task2_thread.join()

# Execute SubTask 3 after SubTask 1 and SubTask 2 are complete
place_pot_with_apple_slices()

# Task Put an Egg in the Fridge, and place a pot containing Apple slices into the refrigerator is done





# Task Description: cook an egg then put it back inside the fridge and chill the bread from the counter then put it on the counter.

# GENERAL TASK DECOMPOSITION
# Decompose and parallelize subtasks where ever possible
# Independent subtasks:
# SubTask 1: Cook an Egg and put it back inside the Fridge. (Skills Required: GoToObject, PickupObject, OpenObject, PutObject, CloseObject, SwitchOn, SwitchOff)
# SubTask 2: Chill the bread from the counter then put it on the counter. (Skills Required: GoToObject, PickupObject, OpenObject, PutObject, CloseObject, )
# We can parallelize SubTask 1 and SubTask 2 because they don't depend on each other.

# CODE
def cook_egg_and_put_in_fridge():
    # 0: SubTask 1: Cook an Egg and put it back inside the Fridge
    # 1: go to the fridge
    GoToObject('Egg')
    # 2: pick up the egg
    PickupObject('Egg')
    # 3: walk towards the microwave
    GoToObject('Microwave')
    # 4: open the microwave door
    OpenObject('Microwave')
    # 5: Put the Egg inside the Microwave
    PutObject('Egg', 'Microwave')
    # 6: Close the Microwave
    CloseObject('Microwave')
    # 7: Switch on Microwave
    SwitchOn('Microwave')
    # 8: Wait for a while to let the egg cook.
    time.sleep(5)
    # 9: Switch off Microwave
    SwitchOff('Microwave')
    # 10: Open the Microwave door
    OpenObject('Microwave')
    # 11: Take the Egg out
    PickupObject('Egg')
    # 12: Close the Microwave
    CloseObject('Microwave')
    # 11: Go to the Fridge
    GoToObject('Fridge')
    # 12: Open the Fridge
    OpenObject('Fridge')
    # 13: Put the Egg inside to cool it
    PutObject('Egg', 'Fridge')
    # 14: Close the Fridge
    CloseObject('Fridge')

def chill_bread_and_put_on_counter():
    # 0: SubTask 2: Chill the bread from the counter then put it on the counter
    # 1: Go to the Bread
    GoToObject('Bread')
    # 2: Grab the bread
    PickupObject('Bread')
    # 3: Go to Fridge.
    GoToObject('Fridge')
    # 4: Open Fridge
    OpenObject('Fridge')
    # 5: Put Bread in Fridge
    PutObject('Bread', 'Fridge')
    # 6: Close Fridge
    CloseObject('Fridge')
    # 7: Wait for a while to let the bread c0ol.
    time.sleep(5)
    # 8: Open Fridge
    OpenObject('Fridge')
    # 9: Take bread out
    PickupObject('Bread')
    # 10: Close Fridge
    CloseObject('Fridge')
    # 11: Go to the counter.
    GoToObject('Countertop')
    # 12: Put the bread on the counter.
    PutObject('Bread', 'CounterTop')

# Parallelize SubTask 1 and SubTask 2
task1_thread = threading.Thread(target=cook_egg_and_put_in_fridge)
task2_thread = threading.Thread(target=chill_bread_and_put_on_counter)

# Start executing SubTask 1 and SubTask 2 in parallel
task1_thread.start()
task2_thread.start()

# Wait for both SubTask 1 and SubTask 2 to finish
task1_thread.join()
task2_thread.join()

# Task cook an egg then put it back inside the fridge and chill the bread from the counter then put it on the counter is done





# Task Description: Make a sandwich with sliced lettuce, sliced tomato, sliced bread and serve it on a washed plate.

# GENERAL TASK DECOMPOSITION
# Decompose and parallelize subtasks where ever possible
# Independent subtasks:
# SubTask 1: Slice the Lettuce, Tomato, and Bread. (Skills Required: GoToObject, PickupObject, SliceObject, PutObject)
# SubTask 2: Wash the Plate. (Skills Required: GoToObject, PickupObject, PutObject, SwitchOn, SwitchOff)
# SubTask 3: Assemble the Sandwich. (Skills Required: GoToObject, PickupObject, PutObject)
# We can parallelize SubTask 1 and SubTask 2 because they don't depend on each other.

# CODE
def slice_ingredients():
    # 0: SubTask 1: Slice the Lettuce, Tomato, and Bread
    # 1: Go to the Knife.
    GoToObject('Knife')
    # 2: Pick up the Knife.
    PickupObject('Knife')
    # 3: Go to the Lettuce.
    GoToObject('Lettuce')
    # 4: Slice the Lettuce.
    SliceObject('Lettuce')
    # 5: Go to the Tomato.
    GoToObject('Tomato')
    # 6: Slice the Tomato.
    SliceObject('Tomato')
    # 7: Go to the Bread.
    GoToObject('Bread')
    # 8: Slice the Bread.
    SliceObject('Bread')
    # 9: Go to the countertop.
    GoToObject('CounterTop')
    # 10: Put the Knife back on the CounterTop.
    PutObject('Knife', 'CounterTop')

def wash_plate():
    # 0: SubTask 2: Wash the Plate
    # 1: Go to the Plate.
    GoToObject('Plate')
    # 2: Pick up the Plate.
    PickupObject('Plate')
    # 3: Go to the Sink.
    GoToObject('Sink')
    # 4: Put the plate inside the sink
    PutObject('Plate', 'Sink')
    # 5: Switch on the Faucet to clean the Plate
    SwitchOn('Faucet')
    # 6: Wait for a while to let the plate clean.
    time.sleep(5)
    # 7: Switch off the Faucet
    SwitchOff('Faucet')
    # 8: Pick up the clean Plate.
    PickupObject('Plate')
    # 9: Go to the CounterTop.
    GoToObject('CounterTop')
    # 10: Place the Plate on the CounterTop
    PutObject('Plate', 'CounterTop')

def assemble_sandwich():
    # 0: SubTask 3: Assemble the Sandwich
    # 1: Go to the Bread slice.
    GoToObject('Bread')
    # 2: Pick up the Bread slice.
    PickupObject('Bread')
    # 3: Go to the Plate.
    GoToObject('Plate')
    # 4: Place a slice of Bread on the Plate
    PutObject('Bread', 'Plate')
    # 5: Go to the Lettuce.
    GoToObject('Lettuce')
    # 6: Pick up the Lettuce.
    PickupObject('Lettuce')
    # 7: Go to the Plate.
    GoToObject('Plate')
    # 8: Place a slice of Lettuce on the Plate
    PutObject('Lettuce', 'Plate')
    # 9: Go to the Tomato.
    GoToObject('Tomato')
    # 10: Pick up the Tomato.
    PickupObject('Tomato')
    # 11: Go to the Plate.
    GoToObject('Plate')
    # 12: Place a slice of Tomato on the Plate
    PutObject('Tomato', 'Plate')
    # 13: Go to another Bread slice.
    GoToObject('Bread')
    # 14: Pick up the Bread slice.
    PickupObject('Bread')
    # 15: Go to the Plate.
    GoToObject('Plate')
    # 17: Place another slice of Bread on top of the Plate.
    PutObject('Bread', 'Plate')

# Parallelize SubTask 1 and SubTask 2
task1_thread = threading.Thread(target=slice_ingredients)
task2_thread = threading.Thread(target=wash_plate)

# Start executing SubTask 1 and SubTask 2 in parallel
task1_thread.start()
task2_thread.start()

# Wait for both SubTask 1 and SubTask 2 to finish
task1_thread.join()
task2_thread.join()

# Execute SubTask 3 after SubTask 1 and SubTask 2 are complete
assemble_sandwich()

# Task Make a sandwich with sliced lettuce, sliced tomato, sliced bread and serve it on a washed plate is done





# Task Description: fry the potato 

# GENERAL TASK DECOMPOSITION
# Decompose and parallelize subtasks where ever possible
# Independent subtasks:
# SubTask 1: Prepare the Potato. (Skills Required: GoToObject, PickupObject, SliceObject, PutObject)
# SubTask 2: Fry the Potato. (Skills Required: GoToObject, PickupObject, PutObject, SwitchOn, SwitchOff, )
# We can execute SubTask 1 first and then SubTask 2, since they cannot be parallized. 

# CODE
def prepare_potato():
    # 0: SubTask 1: Prepare the Potato
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

def fry_potato():
    # 0: SubTask 2: Fry the Potato
    # 1: Go to the sliced Potato.
    GoToObject('Potato')
    # 2: Pick up the sliced Potato.
    PickupObject('Potato')
    # 3: Go to the Pan.
    GoToObject('Pan')
    # 4: Put the sliced Potato in the Pan.
    PutObject('Potato', 'Pan')
    # 5: Pick up the pan with potato in it.
    PickupObject('Pan')
    # 6: Go to the StoveBurner.
    GoToObject('StoveBurner')
    # 7: Put the Pan on the stove burner.
    PutObject('Pan', 'StoveBurner')
    # 7: Switch on the StoveKnob.
    SwitchOn('StoveKnob')
    # 7: Wait for a while to let the Potato fry.
    time.sleep(5)
    # 8: Switch off the StoveKnob.
    SwitchOff('StoveKnob')
    # 9: Go to the Potato.
    GoToObject('Potato')
    # 10: Pick up the Potato.
    PickupObject('Potato')
    # 11: Go to the Plate.
    GoToObject('Plate')
    # 12: Put the fried Potato on the Plate.
    PutObject('Potato', 'Plate')

# Execute SubTask 1
prepare_potato()

# Execute SubTask 2
fry_potato()

# Task fry the potato is done




# Task Description: Put apple in the fridge 

# GENERAL TASK DECOMPOSITION
# Decompose and parallelize subtasks where ever possible
# Independent subtasks:
# SubTask 1: Put apple in the fridge. (Skills Required: GoToObject, PickupObject, OpenObject, PutObject, CloseObject)
# We can execute SubTask 1.

# CODE
def put_apple_in_fridge():
    # 0: SubTask 1: Put apple in the fridge
    # 1: Go to the Apple.
    GoToObject('Apple')
    # 2: Pick up the Apple.
    PickupObject('Apple')
    # 3: Go to the Fridge.
    GoToObject('Fridge')
    # 4: Open the Fridge.
    OpenObject('Fridge')
    # 5: Put Apple in the Fridge
    PutObject('Apple', 'Fridge')
    # 6: Close Fridge
    CloseObject('Fridge')

# Execute SubTask 1
put_apple_in_fridge()

# Task put apple in the fridge is done

# Task Description: Pick up the bread and use the microwave to heat an object.

# GENERAL TASK DECOMPOSITION 
# Decompose and parallelize subtasks where ever possible
# Independent subtasks:
# SubTask 1: Pick up the bread and heat it in the microwave. (Skills Required: GoToObject, PickupObject, OpenObject, PutObject, CloseObject, SwitchOn, SwitchOff)
# Note: "an object" refers to the bread (most recently mentioned object)
# We can execute SubTask 1.

# CODE
def pickup_bread_and_heat_object():
    # 0: SubTask 1: Pick up the bread and heat an object (the bread)
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

# Task Description: Pickup the apple and wash an object.

# GENERAL TASK DECOMPOSITION 
# Decompose and parallelize subtasks where ever possible
# Independent subtasks:
# SubTask 1: Pickup the apple and wash it. (Skills Required: GoToObject, PickupObject, PutObject, SwitchOn, SwitchOff)
# Note: "an object" refers to the apple (most recently mentioned object)
# We can execute SubTask 1.

# CODE
def pickup_apple_and_wash_object():
    # 0: SubTask 1: Pickup the apple and wash an object (the apple)
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

# Task Description: Clean the table.

# GENERAL TASK DECOMPOSITION 
# Decompose and parallelize subtasks where ever possible
# Independent subtasks:
# SubTask 1: Clean the table by removing all objects from it. (Skills Required: GoToObject, PickupObject, PutObject)
# Note: "clean the table" means to clear all objects from the table surface (CounterTop) and put them elsewhere
# Strategy: Identify objects currently on CounterTop, then move each one to Sink or other location
# We can execute SubTask 1.

# CODE
def clean_table():
    # 0: SubTask 1: Clean the table (remove all objects from CounterTop)
    # Note: In this scenario, CounterTop has Bowl, Mug, and Plate on it
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

# Task Description: Switch on the stove and heat an object.

# GENERAL TASK DECOMPOSITION 
# Decompose and parallelize subtasks where ever possible
# Independent subtasks:
# SubTask 1: Switch on the stove and heat an object using a pan. (Skills Required: GoToObject, SwitchOn, PickupObject, PutObject, SwitchOff)
# Note: To use stove correctly, must first place Pan on StoveBurner, then put food in Pan
# We can execute SubTask 1.

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
    # 10: Put the Tomato in the Pan on StoveBurner.
    PutObject('Tomato', 'Pan')
    # 11: Wait for the food to cook.
    time.sleep(10)
    # 12: Switch off the StoveKnob.
    SwitchOff('StoveKnob')

# Execute SubTask 1
switch_on_stove_and_heat_object()

# Task switch on the stove and heat an object is done
