import os
import requests
import json
import csv

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

    # --- 3. Print Formatted Table ---
    print("\nDependency Graph:")
    
    # Define column widths
    col1_width = 30
    col2_width = 15
    col3_width = 30
    col4_width = 15

    # Header
    header = f"{'Parent (Consumer)':<{col1_width}} {'[Type]':<{col2_width}} | {'Child (Supplier)':<{col3_width}} {'[Type]':<{col4_width}}"
    print(header)
    print("-" * len(header))

    for item in processed_rels:
        # Shorten names if they are too long for the table
        p_name_short = (item['parent_name'][:col1_width-2] + '..') if len(item['parent_name']) > col1_width-2 else item['parent_name']
        c_name_short = (item['child_name'][:col3_width-2] + '..') if len(item['child_name']) > col3_width-2 else item['child_name']
        
        # Display friendly type names
        p_type_disp = "Business" if item['parent_type'] == "business_service" else "Technical"
        c_type_disp = "Business" if item['child_type'] == "business_service" else "Technical"

        print(f"{p_name_short:<{col1_width}} {p_type_disp:<{col2_width}} | {c_name_short:<{col3_width}} {c_type_disp:<{col4_width}}")

    
    print("\n--- Generating Output Files ---")

    # --- OUTPUT 1: Terraform (.tf) ---
    with open("dependencies.tf", "w") as f:
        for item in processed_rels:
            f.write(f"""
resource "pagerduty_service_dependency" "dep_{item['rel_id']}" {{
  dependency {{
    dependent_service {{
      id   = "{item['parent_id']}"
      type = "{item['parent_type']}"
    }}
    supporting_service {{
      id   = "{item['child_id']}"
      type = "{item['child_type']}"
    }}
  }}
}}
""")

    # --- OUTPUT 2: IcePanel JSON (.json) ---
    ice_objs = []
    ice_rels = []
    
    for sid, sname in svc_map.items():
        itype = "system" if type_map[sid] == "business_service" else "app"
        ice_objs.append({ "name": sname, "type": itype, "description": f"Imported ID:{sid}" })
        
    for item in processed_rels:
        ice_rels.append({ "from": item['parent_name'], "to": item['child_name'], "description": "Depends on" })
        
    with open("icepanel_bulk.json", "w") as f:
        json.dump({"objects": ice_objs, "relationships": ice_rels}, f, indent=2)

    # --- OUTPUT 3: Audit CSV (.csv) ---
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

    print(f"Orphans Found: {orph_biz} Business Services, {orph_tech} Technical Services.")
    print("Files created: dependencies.tf, icepanel_bulk.json, pagerduty_audit.csv")

if __name__ == "__main__":
    main()