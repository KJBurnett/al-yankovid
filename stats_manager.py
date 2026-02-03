import json
import os
import logging
import datetime
from config import ARCHIVE_ROOT, USERS_MAP_FILE, STATS_FILE

# Configuration
logger = logging.getLogger("AlYankoVid.Stats")

def load_user_map():
    """Loads user mapping from a local JSON file."""
    if os.path.exists(USERS_MAP_FILE):
        try:
            with open(USERS_MAP_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load user map: {e}")
            return {}
    return {}

USER_MAP = load_user_map()

import personality

def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error("Stats file corrupted, starting fresh.")
            return {"users": {}}
    return {"users": {}}

def save_stats(stats):
    try:
        with open(STATS_FILE, 'w') as f:
            json.dump(stats, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save stats: {e}")

def log_archive(user_uuid, user_number, url, filepath, metadata_path=None, subtitle_path=None):
    stats = load_stats()
    
    if user_uuid not in stats["users"]:
        stats["users"][user_uuid] = {"archives": [], "failures": []}
    
    # Auto-Discovery / Update User Info
    current_name = stats["users"][user_uuid].get("name")
    mapped_name = get_user_name(user_number)
    
    # Update if we have a better name (non-hidden number) or if it's new
    if mapped_name != user_number:
        stats["users"][user_uuid]["name"] = mapped_name
        stats["users"][user_uuid]["phone"] = user_number
    elif not current_name:
         stats["users"][user_uuid]["name"] = user_number # Fallback to number if no name found
    
    entry = {
        "url": url,
        "timestamp": datetime.datetime.now().isoformat(),
        "filepath": filepath,
        "metadata_path": metadata_path,
        "subtitle_path": subtitle_path
    }
    
    stats["users"][user_uuid]["archives"].append(entry)
    save_stats(stats)
    logger.info(f"Logged archive for {user_number}: {url}")

def log_failure(user_uuid, user_number, url, error_message):
    stats = load_stats()
    
    if user_uuid not in stats["users"]:
        stats["users"][user_uuid] = {"archives": [], "failures": []}
    elif "failures" not in stats["users"][user_uuid]:
        stats["users"][user_uuid]["failures"] = []

    # Auto-Discovery / Update User Info (Same logic as archive)
    current_name = stats["users"][user_uuid].get("name")
    mapped_name = get_user_name(user_number)
    
    if mapped_name != user_number:
        stats["users"][user_uuid]["name"] = mapped_name
        stats["users"][user_uuid]["phone"] = user_number
    elif not current_name:
         stats["users"][user_uuid]["name"] = user_number

    entry = {
        "url": url,
        "timestamp": datetime.datetime.now().isoformat(),
        "error": error_message
    }
    
    stats["users"][user_uuid]["failures"].append(entry)
    save_stats(stats)
    logger.info(f"Logged failure for {user_number}: {url}")

def load_historical_index():
    index_path = os.path.join(ARCHIVE_ROOT, 'index.json')
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_archive_index(index):
    if not os.path.exists(ARCHIVE_ROOT):
        os.makedirs(ARCHIVE_ROOT)
    index_path = os.path.join(ARCHIVE_ROOT, 'index.json')
    with open(index_path, 'w') as f:
        json.dump(index, f, indent=4)

def delete_archive(url):
    """Deletes the archived files and removes references from stats and index."""
    import shutil
    
    # 1. Update archive index
    index = load_historical_index()
    if url in index:
        filepath = index[url]
        # Deleting the entire directory because we store video, metadata, and subs in the same timestamp folder
        # Directory structure is: archive/<user_id>/<timestamp>/<files>
        folder_path = os.path.dirname(filepath)
        
        if os.path.exists(folder_path) and "archive" in folder_path:
            try:
                shutil.rmtree(folder_path)
                logger.info(f"Deleted folder: {folder_path}")
            except Exception as e:
                logger.error(f"Failed to delete folder {folder_path}: {e}")
        
        del index[url]
        save_archive_index(index)
    
    # 2. Update stats.json
    stats = load_stats()
    found_in_stats = False
    for user_uuid, data in stats.get("users", {}).items():
        archives = data.get("archives", [])
        new_archives = [a for a in archives if a.get("url") != url]
        if len(new_archives) != len(archives):
            stats["users"][user_uuid]["archives"] = new_archives
            found_in_stats = True
            
    if found_in_stats:
        save_stats(stats)
        
    return True

def get_user_name(number):
    return USER_MAP.get(number, number)

def get_formatted_stats():
    # 1. Load History (Total ever archived)
    historical_index = load_historical_index()
    total_historical = 0
    # Verify historical files still exist
    for path in historical_index.values():
        if os.path.exists(path):
            total_historical += 1

    # 2. Load User Stats (Mapped since feature addition)
    stats = load_stats()
    users = stats.get("users", {})
    
    leaderboard = []
    total_attributed = 0
    
    for number, data in users.items():
        archives = data.get("archives", [])
        
        # Verify existence
        valid_archives = [a for a in archives if os.path.exists(a.get('filepath', ''))]
        count = len(valid_archives)
        
        if count > 0:
            # Use the stored name in stats.json, fallback to map, fallback to UUID
            name = data.get("name") or get_user_name(number) 
            leaderboard.append((name, count, number))
            total_attributed += count
    
    # Sort by count descending
    leaderboard.sort(key=lambda x: x[1], reverse=True)
    
    # 3. Format Response
    msg = [f"Total Archives: {total_historical}"]
    
    leaders_quip = ""
    if leaderboard:
        msg.append("-" * 20)
        for rank, (name, count, number) in enumerate(leaderboard, 1):
            msg.append(f"{rank}. {name}: {count}")
            
        unattributed = total_historical - total_attributed
        if unattributed > 0:
            msg.append(f"— Plus {unattributed} historical relics from the 'Before Times'.")
            
        # Determine Leader(s)
        max_count = leaderboard[0][1]
        leaders = [item[0] for item in leaderboard if item[1] == max_count]
        
        if len(leaders) > 1:
            leaders_quip = personality.get_tie_quip(leaders)
        else:
            leaders_quip = personality.get_leader_quip(leaders[0])
            
    elif total_historical > 0:
        msg.append(f"All {total_historical} archives are currently unattributed relics!")
    else:
        msg.append("\nNo one has claimed any archives yet! Be the first!")
        
    final_msg = "\n".join(msg)
    if leaders_quip:
        final_msg += f"\n\n{leaders_quip}"
        
    return final_msg, None # Second return kept for compatibility but not primary
