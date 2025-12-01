import os
import shutil
import datetime
import logging
import time
import schedule
import threading
import subprocess
import json
import sys
import re
import platform

# === 依赖库检查 ===
try:
    from tqdm import tqdm
except ImportError:
    print("❌ 缺少 tqdm 库！请运行: pip install tqdm")
    time.sleep(5)
    sys.exit(1)

# 尝试导入 Cloudreve SDK
try:
    from cloudreve import CloudreveV4
    CLOUDREVE_AVAILABLE = True
except ImportError:
    CLOUDREVE_AVAILABLE = False
    print("⚠️ 未检测到 cloudreve 库，云同步功能将不可用。")
    print("   请确保已安装: pip install cloudreve")

# === 全局配置 ===
CONFIG_FILE = "config.json"
LOG_FILE = "backup_service.log"
current_config = {}

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

# ==========================================
#      配置模块
# ==========================================

def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=4)
    global current_config
    current_config = cfg

def load_config():
    global current_config
    if not os.path.exists(CONFIG_FILE):
        current_config = run_setup_wizard()
    else:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            current_config = json.load(f)

def run_setup_wizard():
    print("\n" + "="*60)
    print(" ☁️ CloudBackup 通用备份系统 (本地+Cloudreve)")
    print("="*60 + "\n")

    src = input("请输入[源数据]目录路径 > ").strip().replace('"','')
    bk_root = input("请输入[本地仓库]存储路径 > ").strip().replace('"','')
    if not os.path.exists(bk_root): 
        try: os.makedirs(bk_root)
        except: pass
    
    # 7-Zip 检测
    system_type = platform.system()
    if system_type == "Windows":
        sz_path = r"C:\Program Files\7-Zip\7z.exe"
    else:
        sz_path = "7z"

    if system_type == "Windows" and not os.path.exists(sz_path):
        sz_input = input("请手动输入 7z.exe 路径 > ").strip().replace('"','')
        if os.path.exists(sz_input): sz_path = sz_input

    existing_accounts = current_config.get("cr_accounts", [])

    cfg = {
        "source_dir": src,
        "backup_root_dir": bk_root,
        "7zip_path": sz_path,
        "volume_size": "1g",
        "schedule_time": "03:00", 
        "compression_level": 3,
        "cr_accounts": existing_accounts
    }
    
    save_config(cfg)
    return cfg

def run_cloudreve_wizard():
    if not CLOUDREVE_AVAILABLE:
        print("❌ 缺少 cloudreve 库")
        return
    
    while True:
        accounts = current_config.get("cr_accounts", [])
        print("\n" + "="*50)
        print("☁️ Cloudreve 账号管理")
        print("="*50)
        
        if not accounts:
            print("   (当前无配置账号)")
        else:
            for idx, acc in enumerate(accounts):
                print(f"   {idx+1}. [{acc['name']}] -> {acc['url']} ({acc['dir']})")
        
        print("-" * 50)
        print("1. 添加新账号")
        print("2. 清空所有账号")
        print("0. 退出并保存")
        
        choice = input("请选择 > ").strip()
        
        if choice == '1':
            print("\n➕ 添加新账号")
            name = input("账号备注名 (如: NAS/网盘) > ").strip()
            if not name: name = f"Account_{len(accounts)+1}"
            
            url = input(f"站点地址 [例如 http://IP:5212] > ").strip()
            user = input(f"用户账号 [Email] > ").strip()
            pwd = input(f"用户密码 > ").strip()
            
            target_dir = input(f"远程存储目录 [默认为 /Backup] > ").strip()
            if not target_dir: target_dir = "/Backup"
            
            # 测试连接
            print("⏳ 正在测试连接...")
            try:
                conn = CloudreveV4(url)
                conn.login(user, pwd)
                print("✅ 登录成功！")
                
                # 尝试创建目录
                try: conn.create_folder(target_dir)
                except: pass

                new_acc = {
                    "name": name,
                    "url": url,
                    "user": user,
                    "password": pwd,
                    "dir": target_dir
                }
                accounts.append(new_acc)
                current_config["cr_accounts"] = accounts
                save_config(current_config)
                print("💾 账号已保存")
                
            except Exception as e:
                print(f"❌ 连接失败: {e}")
                print("⚠️ 账号未保存，请检查后重试。")
                
        elif choice == '2':
            confirm = input("⚠️ 确定要清空所有 Cloudreve 账号吗? (y/n) > ")
            if confirm.lower() == 'y':
                current_config["cr_accounts"] = []
                save_config(current_config)
                print("🗑️ 已清空")
                
        elif choice == '0':
            break
        else:
            print("输入无效")

# ==========================================
#      核心工具函数
# ==========================================

def get_size(path):
    total_size = 0
    if os.path.isfile(path):
        total_size = os.path.getsize(path)
    else:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try: total_size += os.path.getsize(fp)
                except: pass
    return total_size / 1024 / 1024

def copy_with_progress(src, dst):
    total = 0
    f_list = []
    
    if os.path.isfile(src):
        total = os.path.getsize(src)
        f_list.append((src, total))
        if not os.path.exists(dst): os.makedirs(dst)
    else:
        for r, _, fs in os.walk(src):
            for f in fs:
                fp = os.path.join(r, f)
                try:
                    s = os.path.getsize(fp)
                    total += s
                    f_list.append((fp, s))
                except: pass
        if not os.path.exists(dst): os.makedirs(dst)
    
    with tqdm(total=total, unit='B', unit_scale=True, unit_divisor=1024, desc="🚀 本地复制", ncols=80) as pbar:
        for fp, sz in f_list:
            if os.path.isfile(src):
                target = os.path.join(dst, os.path.basename(src))
            else:
                rel = os.path.relpath(fp, src)
                target = os.path.join(dst, rel)
            
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                with open(fp, 'rb') as fsrc, open(target, 'wb') as fdst:
                    while True:
                        buf = fsrc.read(1024*1024) 
                        if not buf: break
                        fdst.write(buf)
                        pbar.update(len(buf))
                shutil.copystat(fp, target)
            except: 
                pbar.update(sz)

def compress_with_progress(cmd):
    cmd.append("-bsp1") 
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)
    print("📦 正在压缩...")
    with tqdm(total=100, unit="%", desc="🔨 压缩进度", ncols=80, colour='green') as pbar:
        curr = 0
        for line in p.stdout:
            m = re.search(r'\s(\d+)%', line)
            if m:
                val = int(m.group(1))
                if val > curr:
                    pbar.update(val - curr)
                    curr = val
    return p.wait()

def verify_archive(seven_zip_path, archive_path):
    print(f"🔍 正在校验: {os.path.basename(archive_path)} ...")
    cmd = [seven_zip_path, "t", archive_path, "-bsp1", "-y"]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)
        with tqdm(total=100, unit="%", desc="🛡️ 校验进度", ncols=80, colour='cyan') as pbar:
            curr = 0
            for line in p.stdout:
                m = re.search(r'\s(\d+)%', line)
                if m:
                    val = int(m.group(1))
                    if val > curr:
                        pbar.update(val - curr)
                        curr = val
        ret_code = p.wait()
        return ret_code == 0
    except Exception as e:
        print(f"❌ 校验执行出错: {e}")
        return False

# ==========================================
#      Cloudreve 上传模块
# ==========================================

def upload_single_account(acc, local_dir, files_list):
    name = acc['name']
    url = acc['url']
    user = acc['user']
    password = acc['password']
    root_dir = acc['dir']
    
    print(f"\n☁️ [{name}] 连接中...")

    def get_conn():
        c = CloudreveV4(url)
        c.login(user, password)
        return c

    try:
        conn = get_conn()
        date_folder_name = os.path.basename(local_dir)
        
        # 逻辑判断：如果 local_dir 是文件，说明是单文件直传
        # 如果是目录，说明是分卷文件夹，需要在云端也创建同名文件夹
        if os.path.isfile(local_dir):
             remote_target_dir = root_dir 
        else:
             remote_target_dir = f"{root_dir}/{date_folder_name}".replace("//", "/")
             try:
                try: conn.create_folder(root_dir)
                except: pass
                conn.create_folder(remote_target_dir)
             except: pass
        
        total_files = len(files_list)
        print(f"   📂 远程目标: {remote_target_dir}")
        
        for idx, fname in enumerate(files_list):
            if os.path.isfile(local_dir):
                local_path = local_dir
            else:
                local_path = os.path.join(local_dir, fname)
            
            remote_uri = f"{remote_target_dir}/{fname}".replace("//", "/")
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    suffix = "" if attempt == 0 else f" (🔄 重试 {attempt})"
                    print(f"   ⬆️ [{idx+1}/{total_files}] 上传: {fname}{suffix}")
                    conn.upload(local_path, remote_uri)
                    break 
                except Exception as e:
                    err_msg = str(e)
                    # 40004: Object existed (文件已存在)
                    if "40004" in err_msg or "Object existed" in err_msg:
                        print(f"   ⚠️ 文件已存在，自动跳过: {fname}")
                        break
                    
                    if "401" in err_msg or "Login required" in err_msg:
                        print(f"   ⚠️ [{name}] Session过期，重连中...")
                        try: conn = get_conn()
                        except: pass
                    else:
                        print(f"   ❌ 上传错误: {err_msg}")
                        if attempt == max_retries - 1:
                            return False, f"[{name}] ❌ 失败: {fname}"
        
        print(f"   ✅ [{name}] 同步完成")
        return True, f"[{name}] ✅ 成功"
        
    except Exception as e:
        err = str(e)
        print(f"   ❌ [{name}] 严重错误: {err}")
        return False, f"[{name}] ❌ 失败: {err[:30]}..."

def upload_to_all_cloudreve(local_target_path):
    if not CLOUDREVE_AVAILABLE: return False
    accounts = current_config.get("cr_accounts", [])
    if not accounts: 
        print("⏩ 未配置云端账号，跳过上传")
        return False

    files_to_upload = []
    
    if os.path.isfile(local_target_path):
        files_to_upload = [os.path.basename(local_target_path)]
        scan_dir = local_target_path 
    else:
        scan_dir = local_target_path
        files_to_upload = sorted([f for f in os.listdir(scan_dir) if ".7z" in f])

    if not files_to_upload: return False

    print(f"\n🚀 开始多云端同步 (共 {len(accounts)} 个目标)...")
    
    results = []
    for acc in accounts:
        success, msg = upload_single_account(acc, scan_dir, files_to_upload)
        results.append(msg)
    
    print("\n📊 云同步报告:")
    for r in results: print(r)
    return True

# ==========================================
#      开发者工具 (测试/清理)
# ==========================================

def run_test_mode():
    print("\n⚠️  压力测试模式")
    gb = input("输入测试大小(GB) [0.5]: ").strip()
    try: target = float(gb) if gb else 0.5
    except: target = 0.5
    
    print(f"🧪 生成 {target}GB 随机测试数据...")
    test_src = os.path.join(os.getcwd(), "TEMP_TEST_DATA")
    if not os.path.exists(test_src): os.makedirs(test_src)
    
    f_path = os.path.join(test_src, "random.dat")
    chunk = 5*1024*1024 
    total = int(target * 1024**3 / chunk)
    if total == 0: total = 1
    
    with open(f_path, 'wb') as f, tqdm(total=total, unit="块", desc="生成数据") as pbar:
        pool = os.urandom(chunk)
        for _ in range(total):
            f.write(pool)
            pbar.update(1)
            
    # 临时替换配置
    real_src = current_config["source_dir"]
    current_config["source_dir"] = test_src
    
    print(f"\n🚀 开始测试流程...")
    try:
        backup_job(is_test=True, enable_upload=False) # 默认测试不上传云端，防垃圾
    finally:
        current_config["source_dir"] = real_src
        try: shutil.rmtree(test_src)
        except: pass
    print("✅ 测试结束")

def run_deltest():
    print("\n🗑️  清理测试残留")
    backup_root = current_config.get("backup_root_dir")
    if not backup_root: return
    
    for d in os.listdir(backup_root):
        if "_TEST" in d:
            full_path = os.path.join(backup_root, d)
            print(f"   🔥 删除: {d}")
            try: shutil.rmtree(full_path)
            except: pass
    print("✅ 清理完成")

# ==========================================
#      主备份逻辑
# ==========================================

def backup_job(is_test=False, enable_upload=True):
    cfg = current_config
    start_time = datetime.datetime.now()
    tag_prefix = "[🧪测试]" if is_test else "[🚀正式]"
    
    print(f"\n⏰ {tag_prefix} 任务启动 [{start_time.strftime('%H:%M:%S')}]")
    logging.info(f"Backup task started")

    d_str = start_time.strftime("%y.%m.%d")
    if is_test: d_str += "_TEST"
    t_str = start_time.strftime("%H%M%S")
    
    daily_root = os.path.join(cfg["backup_root_dir"], d_str)
    raw_dir = os.path.join(daily_root, f"raw_{t_str}")
    
    source_name = os.path.basename(cfg["source_dir"].rstrip("\\/"))
    if not source_name: source_name = "backup"
    
    # 策略判断
    total_mb = get_size(cfg["source_dir"])
    is_large_file = total_mb >= 1000 # 1000MB 阈值
    
    if is_large_file:
        print(f"   ⚖️ 策略: 大文件({total_mb:.0f}MB) -> 分卷压缩")
        archive_store_dir = os.path.join(daily_root, f"{source_name}_Split_{t_str}")
        archive_name = os.path.join(archive_store_dir, f"{source_name}.7z")
        split_arg = f"-v{cfg['volume_size']}" 
    else:
        print(f"   ⚖️ 策略: 小文件({total_mb:.0f}MB) -> 单文件归档")
        archive_store_dir = daily_root
        archive_name = os.path.join(archive_store_dir, f"{source_name}_{t_str}.7z")
        split_arg = "-v999g" 

    try:
        os.makedirs(archive_store_dir, exist_ok=True)
        os.makedirs(raw_dir, exist_ok=True)
        
        # 1. 镜像
        copy_with_progress(cfg["source_dir"], raw_dir)
        
        # 2. 压缩
        cmd = [cfg["7zip_path"], "a", archive_name, os.path.join(raw_dir, "*"), 
               split_arg, f"-mx={cfg['compression_level']}", "-mmt=on", "-y"]
        
        if compress_with_progress(cmd) == 0:
            print("✅ 归档成功，清理临时文件...")
            try: shutil.rmtree(raw_dir)
            except: pass
            
            # 3. 校验
            verify_target = archive_name
            if is_large_file and not os.path.exists(archive_name) and os.path.exists(archive_name + ".001"):
                verify_target = archive_name + ".001"
            
            if verify_archive(cfg["7zip_path"], verify_target):
                print(f"📦 本地备份完成! 耗时: {(datetime.datetime.now() - start_time).seconds}s")
                
                # 4. 上传
                if enable_upload and not is_test:
                    # 如果是大文件分卷，上传整个文件夹；如果是单文件，只传文件
                    upload_target = archive_store_dir if is_large_file else archive_name
                    upload_to_all_cloudreve(upload_target)
            else:
                 print("❌ 校验失败")
        else:
            print("❌ 压缩失败")

    except Exception as e:
        print(f"❌ 异常: {e}")
        logging.error(f"Error: {e}")
    finally:
        if not is_test: print("\n指令 > ", end="")

def run_scheduler_thread():
    print(f"⏰ 定时任务已就绪: 每天 {current_config['schedule_time']}")
    schedule.every().day.at(current_config["schedule_time"]).do(backup_job, is_test=False, enable_upload=True)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    setup_logging()
    load_config()
    
    t = threading.Thread(target=run_scheduler_thread, daemon=True)
    t.start()
    
    print("\n" + "="*50)
    print(" ☁️ CloudBackup 通用备份系统")
    print(f"  - 源目录: {current_config.get('source_dir', '未设置')}")
    print(f"  - 备份仓: {current_config.get('backup_root_dir', '未设置')}")
    
    acc_count = len(current_config.get("cr_accounts", []))
    print(f"  - 云节点: {acc_count} 个已挂载")
    
    print("-" * 50)
    print("指令: [backup]立即备份  [test]压力测试  [deltest]清理测试")
    print("      [cloudreve]账号管理  [setup]重置基础  [exit]退出")
    print("="*50 + "\n")

    while True:
        try:
            cmd = input("指令 > ").strip().lower()
            if cmd == 'backup':
                backup_job(enable_upload=True)
            elif cmd == 'test':
                run_test_mode()
            elif cmd == 'deltest':
                run_deltest()
            elif cmd == 'cloudreve':
                run_cloudreve_wizard()
            elif cmd == 'setup': 
                run_setup_wizard()
                load_config()
            elif cmd == 'exit':
                sys.exit(0)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            print(f"❌ 未知错误: {e}")
