from utils.supabase_client import get_supabase
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_schema():
    supabase = get_supabase()
    
    try:
        # Check publyc_personas
        logger.info("Checking publyc_personas schema...")
        res = supabase.table("publyc_personas").select("*").limit(1).execute()
        if res.data:
            logger.info(f"publyc_personas columns: {res.data[0].keys()}")
        else:
            logger.info("publyc_personas table exists but is empty. Can't infer columns easily without data.")
            # If empty, I might try to just insert a dummy to see if it works, or fallback to assuming common names
            
        # Check messages for flags
        logger.info("Checking messages flags column...")
        # We can't select specific column if it doesn't exist, it might error. 
        # But select("*") will return it if it exists.
        res_msgs = supabase.table("messages").select("*").limit(1).execute()
        if res_msgs.data:
            cols = res_msgs.data[0].keys()
            logger.info(f"messages columns: {cols}")
            if "flags" in cols:
                logger.info("flags column FOUND")
            else:
                logger.warning("flags column NOT FOUND")
    except Exception as e:
        logger.error(f"Error checking schema: {e}")

if __name__ == "__main__":
    check_schema()
