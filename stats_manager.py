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
    total_attributed_count = 0
    total_attributed_size_mb = 0
    
    for number, data in users.items():
        archives = data.get("archives", [])
        
        # Verify existence and sum size
        user_valid_archives = 0
        user_size_mb = 0
        
        for a in archives:
            path = a.get('filepath', '')
            if os.path.exists(path):
                user_valid_archives += 1
                try:
                    size_bytes = os.path.getsize(path)
                    user_size_mb += size_bytes / (1024 * 1024)
                except:
                    pass
        
        if user_valid_archives > 0:
            # Use the stored name in stats.json, fallback to map, fallback to UUID
            name = data.get("name") or get_user_name(number) 
            leaderboard.append({
                "name": name, 
                "count": user_valid_archives, 
                "size": user_size_mb,
                "number": number
            })
            total_attributed_count += user_valid_archives
            total_attributed_size_mb += user_size_mb
    
    # Sort by count descending
    leaderboard.sort(key=lambda x: x["count"], reverse=True)
    
    # 3. Format Response
    msg = [f"Total Archives: {total_historical}"]
    
    if total_attributed_size_mb > 1024:
        msg.append(f"Grand Total Size: {total_attributed_size_mb/1024:.2f} GB")
    else:
        msg.append(f"Grand Total Size: {total_attributed_size_mb:.2f} MB")
    
    quips = []
    
    if leaderboard:
        msg.append("-" * 20)
        for rank, item in enumerate(leaderboard, 1):
            size_str = f"{item['size']/1024:.2f} GB" if item['size'] > 1024 else f"{item['size']:.1f} MB"
            msg.append(f"{rank}. {item['name']}: {item['count']} ({size_str})")
            
        unattributed = total_historical - total_attributed_count
        if unattributed > 0:
            msg.append(f"— Plus {unattributed} historical relics from the 'Before Times'.")
            
        # Determine Count Leader(s)
        max_count = leaderboard[0]["count"]
        leaders = [item["name"] for item in leaderboard if item["count"] == max_count]
        
        if len(leaders) > 1:
            quips.append(personality.get_tie_quip(leaders))
        else:
            quips.append(personality.get_leader_quip(leaders[0]))
            
        # Determine Storage Leader
        storage_leader_item = max(leaderboard, key=lambda x: x["size"])
        # Only add storage quip if they have a non-trivial amount (e.g. > 100MB) and not already praised for being the only leader? 
        # Actually user asked for it specifically.
        # Avoid double quip if the storage leader is the same as the count leader? 
        # User said "make sure there's a whacky quote for the person with the biggest storage usage too".
        # So we can have two quotes.
        
        quips.append(personality.get_storage_leader_quip(storage_leader_item["name"]))

    elif total_historical > 0:
        msg.append(f"All {total_historical} archives are currently unattributed relics!")
    else:
        msg.append("\nNo one has claimed any archives yet! Be the first!")
        
    final_msg = "\n".join(msg)
    if quips:
        final_msg += "\n\n" + "\n\n".join(quips)
        
    return final_msg, None
