import os
import requests
import json

# Configuration
API_KEY = os.getenv("PAGERDUTY_TOKEN", "")
BASE_URL = "https://api.pagerduty.com"

# Headers
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
    print("Fetching PagerDuty data...")
    svc_map = {}
    type_map = {}
    
    # Fetch content
    tech = get_all_items("services", "services")
    for s in tech:
        svc_map[s['id']] = s.get('name') or s.get('summary')
        type_map[s['id']] = "app" # Map Technical Services to 'Apps'

    biz = get_all_items("business_services", "business_services")
    for s in biz:
        svc_map[s['id']] = s.get('name') or s.get('summary')
        type_map[s['id']] = "system" # Map Business Services to 'Systems'

    relationships = get_all_items("service_dependencies", "relationships")
    
    # IcePanel Bulk Import Structure
    # See: https://docs.icepanel.io/
    # Objects: { name, type, description }
    # Relationships: { sourceName, targetName, description }
    
    objects = []
    links = []
    
    # 1. Create Objects
    for sid, sname in svc_map.items():
        stype = type_map[sid]
        
        # IcePanel recognizable types: 'system', 'app', 'store', 'component'
        
        objects.append({
            "name": sname,
            "type": stype,
            "description": f"Imported from PagerDuty (ID: {sid})"
        })

    # 2. Create Links
    # Note: IcePanel bulk import matches mainly by NAME.
    for r in relationships:
        # parent (dependent) -> child (supporting)
        pid = r.get('dependent_service', {}).get('id')
        cid = r.get('supporting_service', {}).get('id')
        
        if pid in svc_map and cid in svc_map:
            pname = svc_map[pid]
            cname = svc_map[cid]
            
            links.append({
                "from": pname,
                "to": cname,
                "description": "Depends on"
            })

    output_data = {
        "objects": objects,
        "relationships": links
    }

    print("Writing icepanel_bulk.json...")
    with open("icepanel_bulk.json", "w") as f:
        json.dump(output_data, f, indent=2)
    
    print("Done.")

if __name__ == "__main__":
    main()