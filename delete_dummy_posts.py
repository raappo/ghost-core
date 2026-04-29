import os
from supabase import create_client

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)

supabase.table("content_farm").delete().in_("id", [7, 8]).execute()
print("Deleted dummy posts 7 and 8.")
