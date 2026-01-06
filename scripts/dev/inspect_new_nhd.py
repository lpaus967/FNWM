"""
Inspect new NHD GeoJSON file schema
"""
import json

geojson_path = r"D:\Personal Projects\FNWM\Testing\Hydrology\nhdFlowline.geojson"

print("=" * 80)
print("INSPECTING NEW NHD GEOJSON")
print("=" * 80)

# Load GeoJSON
print(f"\nLoading: {geojson_path}")
with open(geojson_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

total_features = len(data['features'])
print(f"Total features: {total_features:,}")

# Get first feature properties
first_feature = data['features'][0]
props = first_feature['properties']

print(f"\n{'-'*80}")
print("ALL PROPERTIES (first feature):")
print("-" * 80)
for key in sorted(props.keys()):
    value = props[key]
    if isinstance(value, str) and len(value) > 50:
        value = value[:50] + "..."
    print(f"  {key}: {value}")

print(f"\n{'-'*80}")
print("CHECKING FOR COMMON IDENTIFIER:")
print("-" * 80)

# Look for Common Identifier field
common_id_keys = [k for k in props.keys() if 'common' in k.lower() and 'identifier' in k.lower()]

if common_id_keys:
    for key in common_id_keys:
        print(f"  ✓ Found: '{key}' = {props[key]}")
else:
    print("  Looking for related fields...")
    for key in props.keys():
        if 'comid' in key.lower() or 'identifier' in key.lower() or 'id' in key.lower():
            print(f"    {key}: {props[key]}")

print(f"\n{'-'*80}")
print("SAMPLE FEATURE IDS:")
print("-" * 80)

# Show first 5 features' Common Identifier values
if common_id_keys:
    id_field = common_id_keys[0]
    print(f"Using field: '{id_field}'")
    print(f"\nFirst 10 values:")
    for i in range(min(10, total_features)):
        val = data['features'][i]['properties'].get(id_field)
        print(f"  [{i}] {val}")
