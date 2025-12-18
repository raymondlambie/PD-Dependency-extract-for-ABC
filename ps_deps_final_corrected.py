import os
import requests

# Configuration
API_KEY = os.getenv("PAGERDUTY_TOKEN", "YOUR_API_KEY_HERE")
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
        if r.status_code != 200: break
        d = r.json()
        items.extend(d.get(key_name, []))
        more = d.get('more', False)
        params['offset'] += params['limit']
    return items

def main():
    print("1. Mapping Service Names and Types...")
    svc_map = {}   # Stores ID -> Name
    type_map = {}  # Stores ID -> "service" or "business_service"
    
    # Map Technical Services
    tech_svcs = get_all_items("services", "services")
    for s in tech_svcs:
        svc_map[s['id']] = s.get('name') or s.get('summary')
        type_map[s['id']] = "service" # Terraform type for technical services

    # Map Business Services
    biz_svcs = get_all_items("business_services", "business_services")
    for s in biz_svcs:
        svc_map[s['id']] = s.get('name') or s.get('summary')
        type_map[s['id']] = "business_service" # Terraform type for business services

    print(f"   Mapped {len(svc_map)} total services ({len(tech_svcs)} Technical, {len(biz_svcs)} Business).")

    print("2. Fetching Service Dependencies...")
    relationships = get_all_items("service_dependencies", "relationships")
    
    results = []

    for r in relationships:
        # API JSON: 'dependent_service' is the Consumer (Parent)
        parent_obj = r.get('dependent_service', {})
        parent_id  = parent_obj.get('id')
        
        # API JSON: 'supporting_service' is the Supplier (Child)
        child_obj = r.get('supporting_service', {})
        child_id  = child_obj.get('id')
        
        # Resolve Types using our pre-fetched map (fallback to 'service' if unknown)
        parent_tf_type = type_map.get(parent_id, "service")
        child_tf_type = type_map.get(child_id, "service")

        results.append({
            "rel_id": r['id'],
            "parent_name": svc_map.get(parent_id, f"Unknown ({parent_id})"),
            "parent_id": parent_id,
            "parent_tf_type": parent_tf_type,
            "child_name": svc_map.get(child_id, f"Unknown ({child_id})"),
            "child_id": child_id,
            "child_tf_type": child_tf_type
        })

    # Output Table with Types
    if not results:
        print("No dependencies found.")
    else:
        # Format string for nice columns
        row_fmt = "{:<30} {:<15} | {:<30} {:<15}"
        print("\n" + row_fmt.format("Parent (Consumer)", "[Type]", "Child (Supplier)", "[Type]"))
        print("-" * 95)
        for res in results:
            # Shorten types for display
            p_type_display = "Business" if res['parent_tf_type'] == "business_service" else "Technical"
            c_type_display = "Business" if res['child_tf_type'] == "business_service" else "Technical"
            
            print(row_fmt.format(
                res['parent_name'][:29], 
                p_type_display, 
                res['child_name'][:29], 
                c_type_display
            ))

    # Generate Terraform
    print("\nGenerating dependencies.tf...")
    with open("dependencies.tf", "w") as f:
        for res in results:
            f.write(f"""
resource "pagerduty_service_dependency" "dep_{res['rel_id']}" {{
  dependency {{
    dependent_service {{
      id   = "{res['parent_id']}"
      type = "{res['parent_tf_type']}"
    }}
    supporting_service {{
      id   = "{res['child_id']}"
      type = "{res['child_tf_type']}"
    }}
  }}
}}
""")
    print("Done. File 'dependencies.tf' created/updated.")
    # Created/Modified files during execution:
    print("dependencies.tf")

if __name__ == "__main__":
    main()
