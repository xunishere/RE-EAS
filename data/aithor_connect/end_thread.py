
time.sleep(1)

# 保存安全监测数据和预测数据
save_and_cleanup_monitoring_data()

if total_exec > 0:
    exec = float(success_exec) / float(total_exec)
else:
    exec = 0.0

print (ground_truth)
objs = list([obj for obj in c.last_event.metadata["objects"]])

gcr_tasks = 0.0
gcr_complete = 0.0
for obj_gt in ground_truth:
    obj_name = obj_gt['name']
    state = obj_gt['state']
    contains = obj_gt['contains']
    gcr_tasks += 1
    for obj in objs:
        # if obj_name in obj["name"]:
        #     print (obj)
        if state == 'SLICED':
            if obj_name in obj["name"] and obj["isSliced"]:
                gcr_complete += 1
                break
                
        elif state == 'OFF':
            if obj_name in obj["name"] and not obj["isToggled"]:
                gcr_complete += 1
                break
        
        elif state == 'ON':
            if obj_name in obj["name"] and obj["isToggled"]:
                gcr_complete += 1
                break
        
        elif state == 'HOT':
            if obj_name in obj["name"]:
                print (f"[DEBUG] 检查 {obj['name']}: temperature={obj.get('temperature', 'N/A')}")
                if obj["temperature"] == 'Hot':
                    gcr_complete += 1
                    break
                
        elif state == 'COOKED':
            if obj_name in obj["name"] and obj["isCooked"]:
                gcr_complete += 1
                break
                
        elif state == 'OPENED':
            if obj_name in obj["name"] and obj["isOpen"]:
                gcr_complete += 1
                break
                
        elif state == 'CLOSED':
            if obj_name in obj["name"] and not obj["isOpen"]:
                gcr_complete += 1
                break
                
        elif state == 'PICKED':
            if obj_name in obj["name"] and obj["isPickedUp"]:
                gcr_complete += 1
                break 
        
        # 检查 contains 条件（包括空容器的情况）
        if contains is not None and obj_name in obj["name"]:
            # contains: [] 表示要求容器为空
            if len(contains) == 0:
                if obj['receptacleObjectIds'] is None or len(obj['receptacleObjectIds']) == 0:
                    print (f"✓ {obj_name} 容器为空（符合要求）")
                    gcr_complete += 1
                    break  # ← 只检查第一个匹配的物体
                else:
                    print (f"✗ {obj_name} 应为空，但包含: {obj['receptacleObjectIds']}")
                    break  # ← 只检查第一个匹配的物体
            # contains: [items] 表示要求包含特定物体
            elif len(contains) != 0:
                print (f"\n=== 检查 {obj_name} 的 contains ===")
                print (f"  ground_truth requires: {contains}")
                print (f"  actual receptacleObjectIds: {obj['receptacleObjectIds']}")
                print (f"  is None: {obj['receptacleObjectIds'] is None}")
                print (f"  length: {len(obj['receptacleObjectIds']) if obj['receptacleObjectIds'] else 0}")
                for rec in contains:
                    if obj['receptacleObjectIds'] is not None:
                        # '*' 表示任意物体，只要容器不为空就算完成
                        if rec == '*':
                            if len(obj['receptacleObjectIds']) > 0:
                                print (f"✓ {obj_name} 包含物体: {obj['receptacleObjectIds']}")
                                gcr_complete += 1
                        else:
                            # 检查特定物体
                            for r in obj['receptacleObjectIds']:
                                print (rec, r)
                                if rec in r:
                                    print (rec, r)
                                    gcr_complete += 1
                    else:
                        print(f"DEBUG: {obj_name} 的 receptacleObjectIds 为 None，跳过检查") 
                    
            
             
sr = 0
tc = 0
if gcr_tasks == 0:
    gcr = 1
else:
    gcr = gcr_complete / gcr_tasks

if gcr == 1.0:
    tc = 1 
    
# 注意：max_trans 和 no_trans_gt 已经从 log.txt 读取，不应该再次修改
print (f"no_trans_gt={no_trans_gt}, max_trans={max_trans}, no_trans={no_trans}")

# RU 计算：如果任务完成且没有超过最大转换限制，则 RU = 1
if tc == 1 and no_trans <= max_trans:
    ru = 1
elif max_trans == no_trans_gt and no_trans_gt == no_trans:
    ru = 1
elif max_trans == no_trans_gt:
    ru = 0
else:
    # 避免除零错误
    if max_trans == no_trans_gt:
        ru = 0
    else:
        ru = (max_trans - no_trans) / (max_trans - no_trans_gt)

if tc == 1 and ru == 1:
    sr = 1

print (f"SR:{sr}, TC:{tc}, GCR:{gcr}, Exec:{exec}, RU:{ru}")

# 检查是否有任何安全违规
has_safety_violation = False
if 'predict_data' in globals() and len(predict_data) > 0:
    has_safety_violation = any(record.get('safe', 1) == 0 for record in predict_data)
    if has_safety_violation:
        print(f"⚠️ 检测到安全违规，本次执行不会保存到RAG数据库")

# 只有当任务成功（SR=1）且没有安全违规时，才保存到 RAG 数据库
if sr == 1 and not has_safety_violation:
    try:
        import json
        import sys
        repair_path = os.path.join(os.getcwd(), 'repair')
        if repair_path not in sys.path:
            sys.path.insert(0, repair_path)
        
        # 动态导入 rag-consens 模块
        import importlib.util
        spec = importlib.util.spec_from_file_location("rag_consens", os.path.join(repair_path, "rag-consens.py"))
        rag_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rag_module)
        SafeExecutionDatabase = rag_module.SafeExecutionDatabase
        
        # 从 log 目录读取任务描述
        # 当前脚本在 executable_plan.py 中，需要找到对应的 log 目录
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        # 向上查找包含 log.txt 的目录
        log_dir = current_script_dir
        for _ in range(5):  # 最多向上5层
            if os.path.exists(os.path.join(log_dir, 'log.txt')):
                break
            log_dir = os.path.dirname(log_dir)
        
        task_desc = "Unknown task"
        if os.path.exists(os.path.join(log_dir, 'log.txt')):
            with open(os.path.join(log_dir, 'log.txt'), 'r') as f:
                task_desc = f.readline().strip()  # 第一行是任务描述
        
        env_type = f"FloorPlan{floor_no}"
        
        # 从 action_log 获取完整的动作序列
        actions_list = []
        print(f"[DEBUG] 检查 action_log: 'action_log' in globals() = {'action_log' in globals()}")
        if 'action_log' in globals():
            print(f"[DEBUG] action_log 长度: {len(action_log)}")
            print(f"[DEBUG] action_log 内容: {action_log}")
            actions_list = action_log.copy()  # 直接使用 action_log
        else:
            print("⚠️ action_log 不在 globals() 中，尝试从 monitor.data 提取")
            # 后备方案：从 monitor.data 提取
            monitor = get_safety_monitor()
            if monitor and len(monitor.data) > 0:
                for item in monitor.data:
                    if 'action' in item:
                        actions_list.append({
                            'action': item['action'],
                            'params': item.get('params', {}),
                            'safe': item.get('safe', 1)
                        })
        
        # 保存到 RAG 数据库
        if len(actions_list) > 0:
            db = SafeExecutionDatabase()
            db.add_record(
                actions=actions_list,
                environment=env_type,
                task_description=task_desc
            )
            db.save_database()
            
            print(f"\n{'='*60}")
            print(f"✅ 安全执行记录已保存到 RAG 数据库")
            print(f"   任务: {task_desc}")
            print(f"   环境: {env_type}")
            print(f"   动作数: {len(actions_list)}")
            print(f"{'='*60}\n")
        else:
            print("⚠️ 没有找到可保存的动作序列")
            
    except Exception as e:
        print(f"⚠️ RAG 数据保存失败: {e}")
        import traceback
        traceback.print_exc()

generate_video()