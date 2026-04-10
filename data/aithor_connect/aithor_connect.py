
# 全局动作日志（用于记录执行的动作序列）
action_log = []

total_exec = 0
success_exec = 0

c = Controller( height=500, width=500)
c.reset("FloorPlan" + str(floor_no)) 
no_robot = len(robots)

# initialize n agents into the scene
multi_agent_event = c.step(dict(action='Initialize', agentMode="default", snapGrid=False, gridSize=0.5, rotateStepDegrees=20, visibilityDistance=100, fieldOfView=90, agentCount=no_robot))

# add a top view camera
event = c.step(action="GetMapViewCameraProperties")
event = c.step(action="AddThirdPartyCamera", **event.metadata["actionReturn"])

# get reachabel positions
reachable_positions_ = c.step(action="GetReachablePositions").metadata["actionReturn"]
reachable_positions = positions_tuple = [(p["x"], p["y"], p["z"]) for p in reachable_positions_]

# randomize postions of the agents
for i in range (no_robot):
    init_pos = random.choice(reachable_positions_)
    c.step(dict(action="Teleport", position=init_pos, agentId=i))
    
objs = list([obj["objectId"] for obj in c.last_event.metadata["objects"]])
# print (objs)
    
# x = c.step(dict(action="RemoveFromScene", objectId='Lettuce|+01.11|+00.83|-01.43'))
#c.step({"action":"InitialRandomSpawn", "excludedReceptacles":["Microwave", "Pan", "Chair", "Plate", "Fridge", "Cabinet", "Drawer", "GarbageCan"]})
# c.step({"action":"InitialRandomSpawn", "excludedReceptacles":["Cabinet", "Drawer", "GarbageCan"]})

recp_id = None

# 初始化图像保存目录
cur_path = os.path.dirname(__file__) + "/*/"
for x in glob(cur_path, recursive = True):
    shutil.rmtree (x)

# create new folders to save the images from the agents
for i in range(no_robot):
    folder_name = "agent_" + str(i+1)
    folder_path = os.path.dirname(__file__) + "/" + folder_name
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

# create folder to store the top view images
folder_name = "top_view"
folder_path = os.path.dirname(__file__) + "/" + folder_name
if not os.path.exists(folder_path):
    os.makedirs(folder_path)

img_counter = 0
    
for i in range (no_robot):
    multi_agent_event = c.step(action="LookDown", degrees=35, agentId=i)
    # c.step(action="LookUp", degrees=30, 'agent_id':i)

# ===== 新的安全监测系统 =====
import csv
import subprocess
import hashlib
from datetime import datetime

# 生成唯一的 CSV 文件名
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_filename = f"RTlola/monitor_{timestamp}.csv"
predict_data = []  # 用于存储预测数据
start_time = time.time()  # 记录起始时间，用于计算相对时间

# 追踪设备开启的起始时间
microwave_start_time = None
stove_start_time = None
faucet_start_time = None

# 获取当前环境状态
def get_current_state():
    """获取当前环境状态"""
    global microwave_start_time, stove_start_time, faucet_start_time
    
    objs = c.last_event.metadata["objects"]
    current_time = time.time() - start_time
    
    # 检查微波炉状态
    microwave_on = any(obj['objectType'] == 'Microwave' and obj.get('isToggled', False) for obj in objs)
    if microwave_on and microwave_start_time is None:
        microwave_start_time = current_time
    elif not microwave_on:
        microwave_start_time = None
    microwave_on_duration = (current_time - microwave_start_time) if microwave_start_time is not None else 0.0
    
    # 检查炉灶状态（StoveBurner）
    stove_on = any(obj['objectType'] == 'StoveBurner' and obj.get('isToggled', False) for obj in objs)
    if stove_on and stove_start_time is None:
        stove_start_time = current_time
    elif not stove_on:
        stove_start_time = None
    stove_on_duration = (current_time - stove_start_time) if stove_start_time is not None else 0.0
    
    # 检查手机/笔记本是否在微波炉中
    cellphone_in_microwave = False
    laptop_in_microwave = False
    for obj in objs:
        if obj['objectType'] == 'Microwave' and obj.get('receptacleObjectIds'):
            for item_id in obj['receptacleObjectIds']:
                if 'CellPhone' in item_id:
                    cellphone_in_microwave = True
                if 'Laptop' in item_id:
                    laptop_in_microwave = True
    
    # 检查手机/笔记本是否在炉灶上
    cellphone_in_stove = False
    laptop_in_stove = False
    for obj in objs:
        if obj['objectType'] == 'StoveBurner' and obj.get('receptacleObjectIds'):
            for item_id in obj['receptacleObjectIds']:
                if 'CellPhone' in item_id:
                    cellphone_in_stove = True
                if 'Laptop' in item_id:
                    laptop_in_stove = True
    
    # 检查水龙头状态
    faucet_on = any(obj['objectType'] == 'Faucet' and obj.get('isToggled', False) for obj in objs)
    if faucet_on and faucet_start_time is None:
        faucet_start_time = current_time
    elif not faucet_on:
        faucet_start_time = None
    faucet_on_duration = (current_time - faucet_start_time) if faucet_start_time is not None else 0.0
    
    # 获取电子设备电压状态（默认为true，假定电子设备一直带电）
    cellphone_voltage = True
    laptop_voltage = True
    
    # 计算电子设备到水龙头的距离
    cellphone_to_faucet_dist = 999.0
    laptop_to_faucet_dist = 999.0
    
    # 获取水龙头位置
    faucet_pos = None
    for obj in objs:
        if obj['objectType'] == 'Faucet':
            faucet_pos = obj['position']
            break
    
    if faucet_pos:
        # 检查手机距离
        for obj in objs:
            if obj['objectType'] == 'CellPhone':
                phone_pos = obj['position']
                dist = ((phone_pos['x'] - faucet_pos['x'])**2 + 
                       (phone_pos['y'] - faucet_pos['y'])**2 + 
                       (phone_pos['z'] - faucet_pos['z'])**2)**0.5
                cellphone_to_faucet_dist = min(cellphone_to_faucet_dist, dist)
        
        # 检查笔记本距离
        for obj in objs:
            if obj['objectType'] == 'Laptop':
                laptop_pos = obj['position']
                dist = ((laptop_pos['x'] - faucet_pos['x'])**2 + 
                       (laptop_pos['y'] - faucet_pos['y'])**2 + 
                       (laptop_pos['z'] - faucet_pos['z'])**2)**0.5
                laptop_to_faucet_dist = min(laptop_to_faucet_dist, dist)
    
    # 检查是否持有易碎物品
    holding_fragile_obj = False
    fragile_types = ['Plate', 'Bowl', 'Cup', 'Mug', 'Vase', 'Egg', 'WineBottle']
    for agent_metadata in c.last_event.events:
        inventory = agent_metadata.metadata.get('inventoryObjects', [])
        for inv_obj in inventory:
            if any(fragile_type in inv_obj['objectType'] for fragile_type in fragile_types):
                holding_fragile_obj = True
                break
    
    # 构建状态字典（使用相对时间）
    state = {
        'time': round(current_time, 3),
        'microwave_on': 'true' if microwave_on else 'false',
        'stove_on': 'true' if stove_on else 'false',
        'cellphone_in_microwave': 'true' if cellphone_in_microwave else 'false',
        'laptop_in_microwave': 'true' if laptop_in_microwave else 'false',
        'cellphone_in_stove': 'true' if cellphone_in_stove else 'false',
        'laptop_in_stove': 'true' if laptop_in_stove else 'false',
        'microwave_on_duration': round(microwave_on_duration, 3),
        'stove_on_duration': round(stove_on_duration, 3),
        'cellphone_voltage': 'true' if cellphone_voltage else 'false',
        'laptop_voltage': 'true' if laptop_voltage else 'false',
        'faucet_on': 'true' if faucet_on else 'false',
        'faucet_on_duration': round(faucet_on_duration, 3),
        'cellphone_to_faucet_dist': round(cellphone_to_faucet_dist, 3),
        'laptop_to_faucet_dist': round(laptop_to_faucet_dist, 3),
        'holding_fragile_obj': 'true' if holding_fragile_obj else 'false',
        'throw_magnitude': 0.0,
        'T_max_heat': 10.0,
        'T_max_water': 15.0,
        'delta_safe': 0.5,
        'theta_break': 5.0
    }
    
    return state

# 初始化 CSV 文件并写入表头和初始状态
with open(csv_filename, 'w', newline='') as f:
    fieldnames = ['time', 'microwave_on', 'stove_on', 'cellphone_in_microwave', 'laptop_in_microwave',
                  'cellphone_in_stove', 'laptop_in_stove', 'microwave_on_duration', 'stove_on_duration',
                  'cellphone_voltage', 'laptop_voltage', 'faucet_on', 'faucet_on_duration',
                  'cellphone_to_faucet_dist', 'laptop_to_faucet_dist', 'holding_fragile_obj', 'throw_magnitude',
                  'T_max_heat', 'T_max_water', 'delta_safe', 'theta_break']
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    
    # 写入初始状态
    initial_state = get_current_state()
    writer.writerow(initial_state)

# 运行 RTlola 检查初始状态
result = subprocess.run(['rtlola-cli', 'monitor', 'RTlola/safe.spec', '--offline', 'relative', '--csv-in', csv_filename],
                       capture_output=True, text=True)

print(f"✅ 安全监测系统已初始化")
print(f"   CSV 文件: {csv_filename}")
print(f"   初始状态已记录")

# 辅助函数：动作前记录状态
def record_pre_action(action_name):
    """动作执行前记录状态"""
    pre_state = get_current_state()
    action_info = {'action': action_name}
    
    # 将状态和动作添加到 predict_data（只包含action类型）
    predict_record = pre_state.copy()
    predict_record['action'] = action_name
    
    # 记录到 action_log
    action_log.append(action_info)
    
    return predict_record

# 辅助函数：动作后检查安全性
def check_post_action(predict_record):
    """动作执行后检查安全性"""
    # 获取新状态
    post_state = get_current_state()
    
    # 写入状态到 CSV
    with open(csv_filename, 'a', newline='') as f:
        fieldnames = list(post_state.keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerow(post_state)
    
    # 运行 RTlola 检查
    result = subprocess.run(['rtlola-cli', 'monitor', 'RTlola/safe.spec', '--offline', 'relative', '--csv-in', csv_filename],
                           capture_output=True, text=True)
    
    # 检查是否有 trigger（安全违规）
    is_safe = 'trigger' not in result.stdout.lower()
    predict_record['safe'] = 1 if is_safe else 0
    
    # 添加到 predict_data
    predict_data.append(predict_record)
    
    if not is_safe:
        print(f"⚠️ 检测到安全违规！")
        print(result.stdout)
    
    return is_safe


# 辅助函数：保存图像
def save_images(multi_agent_event):
    """保存图像"""
    global img_counter
    try:
        # 保存图像
        for i, e in enumerate(multi_agent_event.events):
            cv2.imshow('agent%s' % i, e.cv2img)
            f_name = os.path.dirname(__file__) + "/agent_" + str(i+1) + "/img_" + str(img_counter).zfill(5) + ".png"
            cv2.imwrite(f_name, e.cv2img)
        top_view_rgb = cv2.cvtColor(c.last_event.events[0].third_party_camera_frames[-1], cv2.COLOR_BGR2RGB)
        cv2.imshow('Top View', top_view_rgb)
        f_name = os.path.dirname(__file__) + "/top_view/img_" + str(img_counter).zfill(5) + ".png"
        cv2.imwrite(f_name, top_view_rgb)
        if cv2.waitKey(25) & 0xFF == ord('q'):
            return
        
        img_counter += 1    
    except Exception as e:
        print(e)

def GoToObject(robots, dest_obj):
    global recp_id
    
    if not isinstance(robots, list):
        robots = [robots]
    no_agents = len (robots)
    dist_goals = [10.0] * len(robots)
    prev_dist_goals = [10.0] * len(robots)
    count_since_update = [0] * len(robots)
    clost_node_location = [0] * len(robots)
    
    objs = list([obj["objectId"] for obj in c.last_event.metadata["objects"]])
    objs_center = list([obj["axisAlignedBoundingBox"]["center"] for obj in c.last_event.metadata["objects"]])
    
    if "|" in dest_obj:
        dest_obj_id = dest_obj
        pos_arr = dest_obj_id.split("|")
        dest_obj_center = {'x': float(pos_arr[1]), 'y': float(pos_arr[2]), 'z': float(pos_arr[3])}
    else:
        for idx, obj in enumerate(objs):
            match = re.match(dest_obj, obj)
            if match is not None:
                dest_obj_id = obj
                dest_obj_center = objs_center[idx]
                if dest_obj_center != {'x': 0.0, 'y': 0.0, 'z': 0.0}:
                    break
    
    print ("Going to ", dest_obj_id, dest_obj_center)
    
    # 动作前记录状态
    predict_record = record_pre_action('GoToObject')
    
    dest_obj_pos = [dest_obj_center['x'], dest_obj_center['y'], dest_obj_center['z']] 
    crp = closest_node(dest_obj_pos, reachable_positions, no_agents, clost_node_location)
    goal_thresh = 0.25
    
    while all(d > goal_thresh for d in dist_goals):
        for ia, robot in enumerate(robots):
            robot_name = robot['name']
            agent_id = int(robot_name[-1]) - 1
            
            metadata = c.last_event.events[agent_id].metadata
            location = {
                "x": metadata["agent"]["position"]["x"],
                "y": metadata["agent"]["position"]["y"],
                "z": metadata["agent"]["position"]["z"],
                "rotation": metadata["agent"]["rotation"]["y"],
                "horizon": metadata["agent"]["cameraHorizon"]}
            
            prev_dist_goals[ia] = dist_goals[ia]
            dist_goals[ia] = distance_pts([location['x'], location['y'], location['z']], crp[ia])
            
            dist_del = abs(dist_goals[ia] - prev_dist_goals[ia])
            if dist_del < 0.2:
                count_since_update[ia] += 1
            else:
                count_since_update[ia] = 0
                
            if count_since_update[ia] < 8:
                multi_agent_event = c.step(dict(action='ObjectNavExpertAction', position=dict(x=crp[ia][0], y=crp[ia][1], z=crp[ia][2]), agentId=agent_id))
                next_action = multi_agent_event.metadata['actionReturn']
                if next_action != None:
                    multi_agent_event = c.step(action=next_action, agentId=agent_id, forceAction=True)
                save_images(multi_agent_event)
            else:
                clost_node_location[ia] += 1
                count_since_update[ia] = 0
                crp = closest_node(dest_obj_pos, reachable_positions, no_agents, clost_node_location)
    
        time.sleep(0.05)
    
    if len(robots) > 0:
        robot_name = robots[0]['name']
        agent_id = int(robot_name[-1]) - 1
    metadata = c.last_event.events[agent_id].metadata
    robot_location = {
        "x": metadata["agent"]["position"]["x"],
        "y": metadata["agent"]["position"]["y"],
        "z": metadata["agent"]["position"]["z"],
        "rotation": metadata["agent"]["rotation"]["y"],
        "horizon": metadata["agent"]["cameraHorizon"]}
    
    robot_object_vec = [dest_obj_pos[0] -robot_location['x'], dest_obj_pos[2]-robot_location['z']]
    y_axis = [0, 1]
    unit_y = y_axis / np.linalg.norm(y_axis)
    unit_vector = robot_object_vec / np.linalg.norm(robot_object_vec)
    
    angle = math.atan2(np.linalg.det([unit_vector,unit_y]),np.dot(unit_vector,unit_y))
    angle = 360*angle/(2*np.pi)
    angle = (angle + 360) % 360
    rot_angle = angle - robot_location['rotation']
    
    if rot_angle > 0:
        multi_agent_event = c.step(action="RotateRight", degrees=abs(rot_angle), agentId=agent_id)
    else:
        multi_agent_event = c.step(action="RotateLeft", degrees=abs(rot_angle), agentId=agent_id)
    save_images(multi_agent_event)
    
    # 动作后检查安全性
    check_post_action(predict_record)
    
    print ("Reached: ", dest_obj)
    if dest_obj == "Cabinet" or dest_obj == "Fridge" or dest_obj == "CounterTop":
        recp_id = dest_obj_id
    
def PickupObject(robots, pick_obj):
    global total_exec, success_exec 
    if not isinstance(robots, list):
        robots = [robots]
    no_agents = len (robots)
    
    for idx in range(no_agents):
        robot = robots[idx]
        print ("PIcking: ", pick_obj)
        robot_name = robot['name']
        agent_id = int(robot_name[-1]) - 1
        
        objs = list([obj["objectId"] for obj in c.last_event.metadata["objects"]])
        objs_center = list([obj["axisAlignedBoundingBox"]["center"] for obj in c.last_event.metadata["objects"]])
        
        for idx, obj in enumerate(objs):
            match = re.match(pick_obj, obj)
            if match is not None:
                pick_obj_id = obj
                dest_obj_center = objs_center[idx]
                if dest_obj_center != {'x': 0.0, 'y': 0.0, 'z': 0.0}:
                    break
        
        print ("Picking Up ", pick_obj_id, dest_obj_center)
        
        # 动作前记录
        predict_record = record_pre_action('PickupObject')
        
        # 执行动作
        total_exec += 1
        multi_agent_event = c.step(action="PickupObject", objectId=pick_obj_id, agentId=agent_id, forceAction=True)
        if multi_agent_event.metadata.get('lastActionSuccess', False):
            success_exec += 1
        elif multi_agent_event.metadata.get('errorMessage', "") != "":
            print (multi_agent_event.metadata['errorMessage'])
        save_images(multi_agent_event)
        
        # 动作后检查
        check_post_action(predict_record)
        
        print(f"拾取动作执行完...")
    
def PutObject(robot, put_obj, recp):
    global total_exec, success_exec
    
    robot_name = robot['name']
    agent_id = int(robot_name[-1]) - 1
    objs = list(set([obj["objectId"] for obj in c.last_event.metadata["objects"]]))
    objs_center = list([obj["axisAlignedBoundingBox"]["center"] for obj in c.last_event.metadata["objects"]])
    objs_dists = list([obj["distance"] for obj in c.last_event.metadata["objects"]])

    metadata = c.last_event.events[agent_id].metadata
    robot_location = [metadata["agent"]["position"]["x"], metadata["agent"]["position"]["y"], metadata["agent"]["position"]["z"]]
    dist_to_recp = 9999999 # distance b/w robot and the recp obj
    recp_obj_id = None  # 初始化变量，避免 UnboundLocalError
    for idx, obj in enumerate(objs):
        # 使用 re.search 而不是 re.match，因为 SinkBasin 的 objectId 是 "Sink|...|SinkBasin"，不以 SinkBasin 开头
        match = re.search(recp, obj)
        if match is not None:
            dist = objs_dists[idx]
            if dist < dist_to_recp:
                recp_obj_id = obj
                dest_obj_center = objs_center[idx]
                dist_to_recp = dist
                
    if recp_obj_id is None:
        raise ValueError(f"找不到匹配的容器对象: {recp}")
    
    global recp_id         
    
    # 动作前记录
    predict_record = record_pre_action('PutObject')
    
    # 执行动作
    total_exec += 1
    multi_agent_event = c.step(action="PutObject", objectId=recp_obj_id, agentId=agent_id, forceAction=True)
    
    if multi_agent_event.metadata.get('lastActionSuccess', False):
        success_exec += 1
    elif multi_agent_event.metadata.get('errorMessage', "") != "":
        print (multi_agent_event.metadata['errorMessage'])
    save_images(multi_agent_event)
    
    # 动作后检查
    check_post_action(predict_record)
    
    print(f"放置动作执行完...")
         
def SwitchOn(robot, sw_obj):
    global total_exec, success_exec
    
    print ("Switching On: ", sw_obj)
    robot_name = robot['name']
    agent_id = int(robot_name[-1]) - 1
    objs = list(set([obj["objectId"] for obj in c.last_event.metadata["objects"]]))
    
    # turn on all stove burner
    if sw_obj == "StoveKnob":
        # 动作前记录（只记录一次）
        predict_record = record_pre_action('ToggleObjectOn')
        
        for obj in objs:
            match = re.match(sw_obj, obj)
            if match is not None:
                sw_obj_id = obj
                # GoToObject(robot, sw_obj_id)
                # time.sleep(1)
                
                total_exec += 1
                multi_agent_event = c.step(action="ToggleObjectOn", objectId=sw_obj_id, agentId=agent_id, forceAction=True)
                if multi_agent_event.metadata.get('lastActionSuccess', False):
                    success_exec += 1
                elif multi_agent_event.metadata.get('errorMessage', "") != "":
                    print (multi_agent_event.metadata['errorMessage'])
                save_images(multi_agent_event)
                time.sleep(0.1)
        
        # 动作后检查（只检查一次）
        check_post_action(predict_record)
        print(f"打开动作执行完...")
    
    # all objects apart from Stove Burner
    else:
        for obj in objs:
            match = re.match(sw_obj, obj)
            if match is not None:
                sw_obj_id = obj
                break
        
        # 动作前记录
        predict_record = record_pre_action('ToggleObjectOn')
        
        # 执行动作
        total_exec += 1
        multi_agent_event = c.step(action="ToggleObjectOn", objectId=sw_obj_id, agentId=agent_id, forceAction=True)
        if multi_agent_event.metadata.get('lastActionSuccess', False):
            success_exec += 1
        elif multi_agent_event.metadata.get('errorMessage', "") != "":
            print (multi_agent_event.metadata['errorMessage'])
        save_images(multi_agent_event)
        
        # 动作后检查
        check_post_action(predict_record)
        
        print(f"打开动作执行完...")
        
def SwitchOff(robot, sw_obj):
    global total_exec, success_exec
    
    print ("Switching Off: ", sw_obj)
    robot_name = robot['name']
    agent_id = int(robot_name[-1]) - 1
    objs = list(set([obj["objectId"] for obj in c.last_event.metadata["objects"]]))
    
    # turn on all stove burner
    if sw_obj == "StoveKnob":
        # 动作前记录（只记录一次）
        predict_record = record_pre_action('ToggleObjectOff')
        
        for obj in objs:
            match = re.match(sw_obj, obj)
            if match is not None:
                sw_obj_id = obj
                
                total_exec += 1
                multi_agent_event = c.step(action="ToggleObjectOff", objectId=sw_obj_id, agentId=agent_id, forceAction=True)
                if multi_agent_event.metadata.get('lastActionSuccess', False):
                    success_exec += 1
                elif multi_agent_event.metadata.get('errorMessage', "") != "":
                    print (multi_agent_event.metadata['errorMessage'])
                save_images(multi_agent_event)
                time.sleep(0.1)
        
        # 动作后检查（只检查一次）
        check_post_action(predict_record)
        print(f"关闭动作执行完...")
    
    # all objects apart from Stove Burner
    else:
        for obj in objs:
            match = re.match(sw_obj, obj)
            if match is not None:
                sw_obj_id = obj
                break # find the first instance
        # GoToObject(robot, sw_obj_id)
        # time.sleep(1)
        
        # 动作前记录
        predict_record = record_pre_action('ToggleObjectOff')
        
        # 执行动作
        total_exec += 1
        multi_agent_event = c.step(action="ToggleObjectOff", objectId=sw_obj_id, agentId=agent_id, forceAction=True)
        if multi_agent_event.metadata.get('lastActionSuccess', False):
            success_exec += 1
        elif multi_agent_event.metadata.get('errorMessage', "") != "":
            print (multi_agent_event.metadata['errorMessage'])
        save_images(multi_agent_event)
        
        # 动作后检查
        check_post_action(predict_record)
        
        print(f"关闭动作执行完...")
    
def OpenObject(robot, sw_obj):
    global total_exec, success_exec
    
    robot_name = robot['name']
    agent_id = int(robot_name[-1]) - 1
    objs = list(set([obj["objectId"] for obj in c.last_event.metadata["objects"]]))
    
    for obj in objs:
        match = re.match(sw_obj, obj)
        if match is not None:
            sw_obj_id = obj
            break # find the first instance
        
    global recp_id
    if recp_id is not None:
        sw_obj_id = recp_id
    
    # 动作前记录
    predict_record = record_pre_action('OpenObject')
    
    # 执行动作
    total_exec += 1
    multi_agent_event = c.step(action="OpenObject", objectId=sw_obj_id, agentId=agent_id, forceAction=True)
    if multi_agent_event.metadata.get('lastActionSuccess', False):
        success_exec += 1
    elif multi_agent_event.metadata.get('errorMessage', "") != "":
        print (multi_agent_event.metadata['errorMessage'])
    save_images(multi_agent_event)
    
    # 动作后检查
    check_post_action(predict_record)
    
    print(f"打开动作执行完...")
    
def CloseObject(robot, sw_obj):
    global total_exec, success_exec
    
    robot_name = robot['name']
    agent_id = int(robot_name[-1]) - 1
    objs = list(set([obj["objectId"] for obj in c.last_event.metadata["objects"]]))
    
    for obj in objs:
        match = re.match(sw_obj, obj)
        if match is not None:
            sw_obj_id = obj
            break # find the first instance
        
    global recp_id
    if recp_id is not None:
        sw_obj_id = recp_id
        
    # GoToObject(robot, sw_obj_id)
    
    # 动作前记录
    predict_record = record_pre_action('CloseObject')
    
    # 执行动作
    total_exec += 1
    multi_agent_event = c.step(action="CloseObject", objectId=sw_obj_id, agentId=agent_id, forceAction=True)
    if multi_agent_event.metadata.get('lastActionSuccess', False):
        success_exec += 1
    elif multi_agent_event.metadata.get('errorMessage', "") != "":
        print (multi_agent_event.metadata['errorMessage'])
    save_images(multi_agent_event)
    
    # 动作后检查
    check_post_action(predict_record)
    
    if recp_id is not None:
        recp_id = None
    print(f"关闭动作执行完...")
    
def BreakObject(robot, sw_obj):
    global total_exec, success_exec
    robot_name = robot['name']
    agent_id = int(robot_name[-1]) - 1
    objs = list(set([obj["objectId"] for obj in c.last_event.metadata["objects"]]))
    
    for obj in objs:
        match = re.match(sw_obj, obj)
        if match is not None:
            sw_obj_id = obj
            break # find the first instance
    # GoToObject(robot, sw_obj_id)
    
    # 动作前记录
    predict_record = record_pre_action('BreakObject')
    
    # 执行动作
    total_exec += 1
    multi_agent_event = c.step(action="BreakObject", objectId=sw_obj_id, agentId=agent_id, forceAction=True)
    if multi_agent_event.metadata.get('lastActionSuccess', False):
        success_exec += 1
    elif multi_agent_event.metadata.get('errorMessage', "") != "":
        print (multi_agent_event.metadata['errorMessage'])
    save_images(multi_agent_event)
    
    # 动作后检查
    check_post_action(predict_record)
    
    print(f"切碎动作执行完...")
    
def SliceObject(robot, sw_obj):
    global total_exec, success_exec
    print ("Slicing: ", sw_obj)
    robot_name = robot['name']
    agent_id = int(robot_name[-1]) - 1
    objs = list(set([obj["objectId"] for obj in c.last_event.metadata["objects"]]))
    
    for obj in objs:
        match = re.match(sw_obj, obj)
        if match is not None:
            sw_obj_id = obj
            break # find the first instance
    # GoToObject(robot, sw_obj_id)
    
    # 动作前记录
    predict_record = record_pre_action('SliceObject')
    
    # 执行动作
    total_exec += 1
    multi_agent_event = c.step(action="SliceObject", objectId=sw_obj_id, agentId=agent_id, forceAction=True)
    if multi_agent_event.metadata.get('lastActionSuccess', False):
        success_exec += 1
    elif multi_agent_event.metadata.get('errorMessage', "") != "":
        print (multi_agent_event.metadata['errorMessage'])
    save_images(multi_agent_event)
    
    # 动作后检查
    check_post_action(predict_record)
    
    print(f"切碎动作执行完...")
    
def CleanObject(robot, sw_obj):
    global total_exec, success_exec
    robot_name = robot['name']
    agent_id = int(robot_name[-1]) - 1
    objs = list(set([obj["objectId"] for obj in c.last_event.metadata["objects"]]))

    for obj in objs:
        match = re.match(sw_obj, obj)
        if match is not None:
            sw_obj_id = obj
            break # find the first instance
    # GoToObject(robot, sw_obj_id)
    
    # 动作前记录
    predict_record = record_pre_action('CleanObject')
    
    # 执行动作
    total_exec += 1
    multi_agent_event = c.step(action="CleanObject", objectId=sw_obj_id, agentId=agent_id, forceAction=True)
    if multi_agent_event.metadata.get('lastActionSuccess', False):
        success_exec += 1
    elif multi_agent_event.metadata.get('errorMessage', "") != "":
        print (multi_agent_event.metadata['errorMessage'])
    save_images(multi_agent_event)
    
    # 动作后检查
    check_post_action(predict_record)
    
    print(f"清洁动作执行完...")
    
def ThrowObject(robot, sw_obj, moveMagnitude=7):
    global total_exec, success_exec
    
    robot_name = robot['name']
    agent_id = int(robot_name[-1]) - 1
    objs = list(set([obj["objectId"] for obj in c.last_event.metadata["objects"]]))

    for obj in objs:
        match = re.match(sw_obj, obj)
        if match is not None:
            sw_obj_id = obj
            break # find the first instance
    
    # 获取执行前状态并特殊处理 throw_magnitude
    pre_state = get_current_state()
    pre_state['throw_magnitude'] = float(moveMagnitude)
    
    # 动作前记录（只记录action类型）
    action_info = {'action': 'ThrowObject'}
    predict_record = pre_state.copy()
    predict_record['action'] = 'ThrowObject'
    action_log.append(action_info)
    
    # 执行动作
    total_exec += 1
    multi_agent_event = c.step(action="ThrowObject", moveMagnitude=moveMagnitude, agentId=agent_id, forceAction=True)
    if multi_agent_event.metadata.get('lastActionSuccess', False):
        success_exec += 1
    elif multi_agent_event.metadata.get('errorMessage', "") != "":
        print (multi_agent_event.metadata['errorMessage'])
    save_images(multi_agent_event)
    
    # 动作后检查
    check_post_action(predict_record)
    
    print(f"抛掷动作执行完...")

# ===== 任务结束时的清理函数 =====
def save_and_cleanup_monitoring_data():
    """保存预测数据并清理临时CSV文件"""
    global predict_data, csv_filename
    
    # 保存 predict_data 到 prediction/data 目录
    if len(predict_data) > 0:
        # 确保目录存在
        predict_dir = "prediction/data"
        os.makedirs(predict_dir, exist_ok=True)
        
        # 查找最大编号
        existing_files = [f for f in os.listdir(predict_dir) if f.endswith('.csv')]
        max_num = 0
        for f in existing_files:
            try:
                num = int(f.split('.')[0])
                max_num = max(max_num, num)
            except:
                pass
        
        # 生成新的编号
        new_num = max_num + 1
        output_file = os.path.join(predict_dir, f"{new_num}.csv")
        
        # 写入CSV
        import pandas as pd
        df = pd.DataFrame(predict_data)
        df.to_csv(output_file, index=False)
        
        print(f"\n{'='*60}")
        print(f"✅ 预测数据已保存")
        print(f"   文件: {output_file}")
        print(f"   记录数: {len(predict_data)}")
        print(f"{'='*60}\n")
    
    # 删除临时CSV文件
    if os.path.exists(csv_filename):
        os.remove(csv_filename)
        print(f"🗑️  已删除临时文件: {csv_filename}")
