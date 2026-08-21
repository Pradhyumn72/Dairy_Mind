import os
import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Add imports if not present
    if "from drf_spectacular.utils" not in content:
        # Find where to inject
        if "from rest_framework" in content:
            content = content.replace("from rest_framework", "from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample, OpenApiParameter, OpenApiResponse\nfrom drf_spectacular.types import OpenApiTypes\nfrom rest_framework", 1)
        else:
            content = "from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample, OpenApiParameter, OpenApiResponse\nfrom drf_spectacular.types import OpenApiTypes\n" + content

    # Add @extend_schema_view to ModelViewSets
    viewset_pattern = re.compile(r'class (\w+ViewSet)\(.*ModelViewSet\):')
    for match in viewset_pattern.finditer(content):
        class_name = match.group(1)
        # Check if already decorated
        if f"@extend_schema_view" in content[:match.start()][-100:]:
            continue
        
        resource = class_name.replace("ViewSet", "")
        decorator = f"""@extend_schema_view(
    list=extend_schema(summary="List {resource}", description="List {resource} items"),
    create=extend_schema(summary="Create {resource}", description="Create a new {resource}"),
    retrieve=extend_schema(summary="Retrieve {resource}", description="Get {resource} details"),
    update=extend_schema(summary="Update {resource}", description="Full update {resource}"),
    partial_update=extend_schema(summary="Partial Update {resource}", description="Partial update {resource}"),
    destroy=extend_schema(summary="Delete {resource}", description="Delete {resource}")
)
"""
        content = content.replace(match.group(0), decorator + match.group(0))

    # Add @extend_schema to custom @action methods
    action_pattern = re.compile(r'(@action[^\n]+)\n\s+def (\w+)\(self, request')
    for match in action_pattern.finditer(content):
        action_line = match.group(1)
        method_name = match.group(2)
        if "extend_schema" in content[:match.start()][-100:]:
            continue
            
        summary = method_name.replace("_", " ").title()
        decorator = f"""@extend_schema(summary="{summary}", description="{summary} endpoint")\n    {action_line}"""
        content = content.replace(action_line, decorator)
        
    # Add @extend_schema to APIView methods
    apiview_pattern = re.compile(r'class (\w+View)\(APIView\):')
    # This is slightly harder to parse methods inside, but we can just decorate the methods directly
    get_pattern = re.compile(r'(?<!def )def get\(self, request')
    post_pattern = re.compile(r'(?<!def )def post\(self, request')
    
    # We will just do a simple replacement for get and post
    if "APIView" in content:
        content = re.sub(r'(\s+)def get\(self, request', r'\1@extend_schema(summary="Get Details")\1def get(self, request', content)
        content = re.sub(r'(\s+)def post\(self, request', r'\1@extend_schema(summary="Submit Data")\1def post(self, request', content)

    with open(filepath, 'w') as f:
        f.write(content)

import glob
for app in ['accounts', 'milk', 'health', 'breeding', 'costs', 'vetreport', 'forecast']:
    filepath = f"apps/{app}/views.py"
    if os.path.exists(filepath):
        process_file(filepath)
        print(f"Processed {filepath}")

