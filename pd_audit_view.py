import os
import requests
import json
import csv
import shutil

# Configuration
# Ensure you have 'export PAGERDUTY_TOKEN=...' set in your terminal
API_KEY = os.getenv("PAGERDUTY_TOKEN", "")
BASE_URL = "https://api.pagerduty.com"

headers = {
    "Authorization": f"Token token={API_KEY}",
    "Accept": "application/vnd.pagerduty+json;version=2",
    "Content-Type": "application/json"
}

def get_all_items(endpoint, key_name):
    items = []
    params = {'limit': 100, 'offset': 0}
    more = True
    while more:
        r = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params)
        if r.status_code != 200: 
            print(f"Error fetching {endpoint}: {r.status_code}")
            break
        d = r.json()
        items.extend(d.get(key_name, []))
        more = d.get('more', False)
        params['offset'] += params['limit']
    return items

def main():
    # --- 1. Fetching Services ---
    print("Fetching PagerDuty Data...")
    svc_map = {}   # ID -> Name
    type_map = {}  # ID -> 'service' or 'business_service'
    
    # 1a. Fetch Technical Services
    tech_svcs = get_all_items("services", "services")
    for s in tech_svcs:
        sid = s['id']
        name = s.get('name') or s.get('summary')
        svc_map[sid] = name
        type_map[sid] = "service"

    # 1b. Fetch Business Services
    biz_svcs = get_all_items("business_services", "business_services")
    for s in biz_svcs:
        sid = s['id']
        name = s.get('name') or s.get('summary')
        svc_map[sid] = name
        type_map[sid] = "business_service"

    # --- 2. Fetching & Processing Dependencies ---
    relationships = get_all_items("service_dependencies", "relationships")
    
    # Track usage to find orphans
    parents_set = set() # Consumers
    children_set = set() # Suppliers
    
    processed_rels = []

    for r in relationships:
        parent_obj = r.get('dependent_service', {})
        parent_id  = parent_obj.get('id')
        
        child_obj = r.get('supporting_service', {})
        child_id  = child_obj.get('id')
        
        if parent_id: parents_set.add(parent_id)
        if child_id:  children_set.add(child_id)

        p_name = svc_map.get(parent_id, "Unknown")
        c_name = svc_map.get(child_id, "Unknown")
        p_type = type_map.get(parent_id, "service")
        c_type = type_map.get(child_id, "service")

        processed_rels.append({
            "rel_id": r['id'],
            "parent_name": p_name,
            "parent_id": parent_id,
            "parent_type": p_type,
            "child_name": c_name,
            "child_id": child_id,
            "child_type": c_type
        })

    # --- 3. Dynamic Screen Formatting ---
    
    # Get terminal width
    try:
        terminal_width = shutil.get_terminal_size().columns
    except:
        terminal_width = 120 # Fallback default
    
    # Calculate widths
    # We have 4 columns. 
    # Type columns are fixed width (~10 chars).
    # Separators take up ~7 chars (" | ").
    # Remaining space is split between Parent Name and Child Name.
    
    fixed_width = 10 + 10 + 7 # Types + separators
    remaining = max(10, terminal_width - fixed_width)
    name_col_width = int(remaining / 2) - 2

    # Header
    print("\nDependency Graph:")
    header_fmt = f"{{:<{name_col_width}}} {{:<10}} | {{:<{name_col_width}}} {{:<10}}"
    print(header_fmt.format("Parent (Consumer)", "[Type]", "Child (Supplier)", "[Type]"))
    print("-" * min(terminal_width, (name_col_width * 2 + 20)))

    for item in processed_rels:
        # Truncation helper
        def truncate(s, w):
            return (s[:w-2] + '..') if len(s) > w else s

        p_name_short = truncate(item['parent_name'], name_col_width)
        c_name_short = truncate(item['child_name'], name_col_width)
        
        # Display friendly type names
        p_type_disp = "Business" if item['parent_type'] == "business_service" else "Technical"
        c_type_disp = "Business" if item['child_type'] == "business_service" else "Technical"

        print(header_fmt.format(p_name_short, p_type_disp, c_name_short, c_type_disp))

    # --- 4. CSV Export ---
    print("\nWriting pagerduty_audit.csv...")
    csv_columns = ["Report Type", "Service Name", "Service ID", "Service Type", "Depends On (Target)", "Dependency ID"]
    
    with open("pagerduty_audit.csv", "w", newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
        writer.writeheader()
        
        # A. Active Relationships
        for item in processed_rels:
            writer.writerow({
                "Report Type": "Active Relationship",
                "Service Name": item['parent_name'],
                "Service ID": item['parent_id'],
                "Service Type": "Business" if item['parent_type'] == "business_service" else "Technical",
                "Depends On (Target)": item['child_name'],
                "Dependency ID": item['rel_id']
            })
            
        # B. Orphan Business Services (Consume nothing)
        orph_biz = 0
        for s in biz_svcs:
            sid = s['id']
            if sid not in parents_set:
                orph_biz += 1
                writer.writerow({
                    "Report Type": "Orphan Business Service",
                    "Service Name": s.get('name'),
                    "Service ID": sid,
                    "Service Type": "Business",
                    "Depends On (Target)": "NONE",
                    "Dependency ID": "N/A"
                })

        # C. Orphan Technical Services (Unused)
        orph_tech = 0
        for s in tech_svcs:
            sid = s['id']
            if sid not in children_set:
                orph_tech += 1
                writer.writerow({
                    "Report Type": "Orphan Technical Service",
                    "Service Name": s.get('name'),
                    "Service ID": sid,
                    "Service Type": "Technical",
                    "Depends On (Target)": "NONE",
                    "Dependency ID": "N/A"
                })

    print(f"\nAudit Complete. Found {orph_biz} orphaned Business Services and {orph_tech} orphaned Technical Services.")
    print("CSV created: pagerduty_audit.csv")

if __name__ == "__main__":
    main()