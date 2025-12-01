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
    print(" 📦 通用本地备份工具 (含开发者工具)")
    print("="*60 + "\n")

    src = input("请输入[源数据]目录路径 > ").strip().replace('"','')
    bk_root = input("请输入[备份存放]目录路径 > ").strip().replace('"','')
    
    if not os.path.exists(bk_root): 
        try: os.makedirs(bk_root)
        except: pass
    
    system_type = platform.system()
    if system_type == "Windows":
        sz_path = r"C:\Program Files\7-Zip\7z.exe"
    else:
        sz_path = "7z"

    if system_type == "Windows" and not os.path.exists(sz_path):
        sz_input = input("未检测到默认路径，请手动输入 7z.exe 路径 > ").strip().replace('"','')
        if os.path.exists(sz_input): sz_path = sz_input

    cfg = {
        "source_dir": src,
        "backup_root_dir": bk_root,
        "7zip_path": sz_path,
        "volume_size": "1g",
        "schedule_time": "03:00",
        "compression_level": 3
    }
    
    save_config(cfg)
    return cfg

# ==========================================
#      工具函数
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
    
    with tqdm(total=total, unit='B', unit_scale=True, unit_divisor=1024, desc="🚀 复制文件", ncols=80) as pbar:
        for fp, sz in f_list:
            if os.path.isfile(src):
                target = os.path.join(dst, os.path.basename(src))
            else:
                rel_path = os.path.relpath(fp, src)
                target = os.path.join(dst, rel_path)
            
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                with open(fp, 'rb') as fsrc, open(target, 'wb') as fdst:
                    while True:
                        buf = fsrc.read(1024*1024) 
                        if not buf: break
                        fdst.write(buf)
                        pbar.update(len(buf))
                shutil.copystat(fp, target)
            except Exception as e:
                logging.error(f"Copy error {fp}: {e}")
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
    print(f"🔍 校验完整性: {os.path.basename(archive_path)} ...")
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
        logging.error(f"Verification error: {e}")
        return False

# ==========================================
#      开发者工具模块 (Dev Tools)
# ==========================================

def run_test_mode():
    """压力测试模式：生成随机数据并跑一遍流程"""
    print("\n" + "="*50)
    print("🧪 压力测试模式 (Dev Tools)")
    print("="*50)
    
    gb_input = input("请输入测试数据大小(GB) [默认 0.5]: ").strip()
    try: target_gb = float(gb_input) if gb_input else 0.5
    except: target_gb = 0.5

    # 1. 生成随机测试数据
    test_src = os.path.join(os.getcwd(), "TEMP_TEST_DATA")
    if not os.path.exists(test_src): os.makedirs(test_src)
    
    f_path = os.path.join(test_src, "random_garbage.dat")
    chunk_size = 5 * 1024 * 1024 # 5MB chunk
    total_chunks = int(target_gb * 1024**3 / chunk_size)
    if total_chunks == 0: total_chunks = 1
    
    print(f"🔨 正在生成 {target_gb}GB 随机数据...")
    with open(f_path, 'wb') as f, tqdm(total=total_chunks, unit="块", desc="生成数据", ncols=80) as pbar:
        random_bytes = os.urandom(chunk_size) # 复用同一块内存，速度更快
        for _ in range(total_chunks):
            f.write(random_bytes)
            pbar.update(1)
            
    # 2. 临时替换配置
    original_src = current_config["source_dir"]
    current_config["source_dir"] = test_src
    
    print(f"\n🚀 开始模拟备份流程...")
    try:
        backup_job(is_test=True)
        print("\n✅ 测试流程结束")
    except Exception as e:
        print(f"\n❌ 测试过程发生异常: {e}")
    finally:
        # 3. 恢复现场
        current_config["source_dir"] = original_src
        print("🧹 清理临时测试源文件...")
        try: shutil.rmtree(test_src)
        except Exception as e: print(f"清理失败: {e}")

def run_deltest():
    """清理所有 _TEST 结尾的备份文件夹"""
    print("\n" + "="*50)
    print("🗑️  清理测试残留 (deltest)")
    print("="*50)
    
    backup_root = current_config.get("backup_root_dir")
    if not backup_root or not os.path.exists(backup_root):
        print("备份目录无效")
        return

    count = 0
    for d in os.listdir(backup_root):
        # 匹配日期_TEST 或者 source_Split_TEST 等模式
        if "_TEST" in d:
            full_path = os.path.join(backup_root, d)
            if os.path.isdir(full_path):
                print(f"   🔥 删除: {d}")
                try: 
                    shutil.rmtree(full_path)
                    count += 1
                except Exception as e: print(f"删除失败: {e}")
    
    if count == 0:
        print("   (未发现测试残留)")
    else:
        print(f"\n✅ 共清理 {count} 个测试目录")

# ==========================================
#      核心任务逻辑
# ==========================================

def backup_job(is_test=False):
    cfg = current_config
    if not cfg:
        logging.error("No config loaded.")
        return

    start_time = datetime.datetime.now()
    tag = "[🧪测试]" if is_test else "[🚀正式]"
    logging.info(f"{tag} Backup task started")
    print(f"\n⏰ {tag} 任务启动 [{start_time.strftime('%H:%M:%S')}]")

    # 如果是测试模式，日期文件夹加后缀
    d_str = start_time.strftime("%y.%m.%d")
    if is_test: d_str += "_TEST"
    
    t_str = start_time.strftime("%H%M%S")
    
    # 1. 准备目录结构
    daily_root = os.path.join(cfg["backup_root_dir"], d_str)
    raw_dir = os.path.join(daily_root, f"temp_raw_{t_str}")
    
    source_path = cfg["source_dir"]
    source_name = os.path.basename(source_path.rstrip("\\/"))
    if not source_name: source_name = "backup"
    
    # 2. 估算大小并决定策略
    if not is_test: print("📏 计算源文件大小...")
    total_mb = get_size(source_path)
    if not is_test: print(f"   源大小: {total_mb:.2f} MB")
    
    is_large_file = total_mb >= 1000 
    
    if is_large_file:
        if not is_test: print("   ⚖️  策略: 大文件 -> 分卷压缩")
        archive_store_dir = os.path.join(daily_root, f"{source_name}_Split_{t_str}")
        archive_name = os.path.join(archive_store_dir, f"{source_name}.7z")
        split_arg = f"-v{cfg['volume_size']}" 
    else:
        if not is_test: print("   ⚖️  策略: 小文件 -> 单文件归档")
        archive_store_dir = daily_root
        archive_name = os.path.join(archive_store_dir, f"{source_name}_{t_str}.7z")
        split_arg = "-v999g" 

    try:
        os.makedirs(archive_store_dir, exist_ok=True)
        os.makedirs(raw_dir, exist_ok=True)
        
        # 步骤 1: 复制 (镜像)
        copy_with_progress(source_path, raw_dir)
        
        # 步骤 2: 压缩
        cmd = [
            cfg["7zip_path"], "a", archive_name, 
            os.path.join(raw_dir, "*"),
            split_arg, 
            f"-mx={cfg['compression_level']}", 
            "-mmt=on", "-y"
        ]
        
        if compress_with_progress(cmd) == 0:
            if not is_test: print("✅ 归档成功，清理临时文件...")
            try: shutil.rmtree(raw_dir)
            except: pass
            
            # 步骤 3: 校验
            verify_target = archive_name
            if is_large_file and not os.path.exists(archive_name) and os.path.exists(archive_name + ".001"):
                verify_target = archive_name + ".001"
            
            if verify_archive(cfg["7zip_path"], verify_target):
                duration = (datetime.datetime.now() - start_time).seconds
                if not is_test:
                    print(f"📦 备份完成! 耗时: {duration} 秒")
                logging.info(f"Backup success. Duration: {duration}s")
            else:
                logging.error("Verification failed.")
                print("❌ 校验失败")
        else:
            logging.error("7-Zip failed.")
            print("❌ 压缩过程出错")

    except Exception as e:
        logging.error(f"Critical error: {e}", exc_info=True)
        print(f"❌ 发生异常: {e}")
    finally:
        if not is_test: print("\n指令 > ", end="")

# ==========================================
#      主程序
# ==========================================

def run_scheduler_thread():
    schedule.every().day.at(current_config["schedule_time"]).do(backup_job, is_test=False)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    setup_logging()
    load_config()
    
    t = threading.Thread(target=run_scheduler_thread, daemon=True)
    t.start()
    
    print("\n" + "="*50)
    print(" 📦 通用本地备份工具 (Local Auto-Backup)")
    print("    含开发测试工具包")
    print(f"  - 源目录: {current_config.get('source_dir', '未设置')}")
    print(f"  - 备份仓: {current_config.get('backup_root_dir', '未设置')}")
    print("-" * 50)
    print(" 常用指令:")
    print("   [backup]  立即备份")
    print("   [test]    压力测试 (生成随机数据验证流程)")
    print("   [deltest] 清理测试产生的临时文件夹")
    print("   [setup]   重新配置")
    print("   [exit]    退出")
    print("="*50 + "\n")

    while True:
        try:
            cmd = input("指令 > ").strip().lower()
            if cmd == 'backup':
                backup_job(is_test=False)
            elif cmd == 'test':
                run_test_mode()
            elif cmd == 'deltest':
                run_deltest()
            elif cmd == 'setup': 
                run_setup_wizard()
                load_config()
                print("⚠️ 配置已更新，建议重启程序。")
            elif cmd == 'exit':
                sys.exit(0)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            print(f"❌ 未知错误: {e}")
