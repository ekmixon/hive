#!/usr/bin/env python
#
# Generate an operator bundle for publishing to OLM. Copies appropriate files
# into a directory, and composes the ClusterServiceVersion which needs bits and
# pieces of our rbac and deployment files.
#
# Usage ./hack/generate-operator-bundle.py OUTPUT_DIR PREVIOUS_VERSION GIT_NUM_COMMITS GIT_HASH HIVE_IMAGE
#
# Commit count can be obtained with: git rev-list 9c56c62c6d0180c27e1cc9cf195f4bbfd7a617dd..HEAD --count
# This is the first hive commit, if we tag a release we can then switch to using that tag and bump the base version.

import datetime
import os
import sys
import yaml
import shutil

# This script will append the current number of commits given as an arg
# (presumably since some past base tag), and the git hash arg for a final
# version like: 0.1.189-3f73a592
VERSION_BASE = "0.1"

if len(sys.argv) != 6:
    print(
        f"USAGE: {sys.argv[0]} OUTPUT_DIR PREVIOUS_VERSION GIT_NUM_COMMITS GIT_HASH HIVE_IMAGE"
    )

    sys.exit(1)

outdir = sys.argv[1]
prev_version = sys.argv[2]
git_num_commits = sys.argv[3]
git_hash = sys.argv[4]
hive_image = sys.argv[5]

full_version = f"{VERSION_BASE}.{git_num_commits}-sha{git_hash}"
print(f"Generating CSV for version: {full_version}")

if not os.path.exists(outdir):
    os.mkdir(outdir)

version_dir = os.path.join(outdir, full_version)
if not os.path.exists(version_dir):
    os.mkdir(version_dir)

owned_crds = []

# Copy all CSV files over to the bundle output dir:
crd_files = os.listdir('config/crds/')
for file_name in crd_files:
    full_path = os.path.join('config/crds', file_name)
    if (os.path.isfile(os.path.join('config/crds', file_name))):
        dest_path = os.path.join(version_dir, file_name)
        shutil.copy(full_path, dest_path)
        # Read the CRD yaml to add to owned CRDs list
        with open(dest_path, 'r') as stream:
            crd_csv = yaml.load(stream, Loader=yaml.SafeLoader)
            owned_crds.append(
                    {
                        'description': crd_csv['spec']['versions'][0]['schema']['openAPIV3Schema']['description'],
                        'displayName': crd_csv['spec']['names']['kind'],
                        'kind': crd_csv['spec']['names']['kind'],
                        'name': crd_csv['metadata']['name'],
                        'version': crd_csv['spec']['versions'][0]['name'],
                    })

with open('config/templates/hive-csv-template.yaml', 'r') as stream:
    csv = yaml.load(stream, Loader=yaml.SafeLoader)

csv['spec']['customresourcedefinitions']['owned'] = owned_crds

csv['spec']['install']['spec']['clusterPermissions'] = []

# Add our operator role to the CSV:
with open('config/operator/operator_role.yaml', 'r') as stream:
    operator_role = yaml.load(stream, Loader=yaml.SafeLoader)
    csv['spec']['install']['spec']['clusterPermissions'].append(
        {
            'rules': operator_role['rules'],
            'serviceAccountName': 'hive-operator',
        })

# Add our deployment spec for the hive operator:
with open('config/operator/operator_deployment.yaml', 'r') as stream:
    operator = yaml.load_all(stream, Loader=yaml.SafeLoader)
    operator_components = list(operator)
    operator_deployment = operator_components[1]
    csv['spec']['install']['spec']['deployments'][0]['spec'] = operator_deployment['spec']

# Update the deployment to use the defined image:
csv['spec']['install']['spec']['deployments'][0]['spec']['template']['spec']['containers'][0]['image'] = hive_image

# Update the versions to include git hash:
csv['metadata']['name'] = f"hive-operator.v{full_version}"
csv['spec']['version'] = full_version
csv['spec']['replaces'] = f"hive-operator.v{prev_version}"

# Set the CSV createdAt annotation:
now = datetime.datetime.now()
csv['metadata']['annotations']['createdAt'] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

# Write the CSV to disk:
csv_filename = f"hive-operator.v{full_version}.clusterserviceversion.yaml"
csv_file = os.path.join(version_dir, csv_filename)
with open(csv_file, 'w') as outfile:
    yaml.dump(csv, outfile, default_flow_style=False)
print(f"Wrote ClusterServiceVersion: {csv_file}")

