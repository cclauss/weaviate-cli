"""
Utility functions.
"""

import string
import random
import weaviate
from weaviate.rbac.models import RBAC
from typing import Union, List


def get_client_from_context(ctx) -> weaviate.Client:
    """
        Get Configuration object from the specified file.
    :param ctx:
    :return:
    :rtype: semi.config.configuration.Configuration
    """
    return ctx.obj["config"].get_client()


# Insert objects to the replicated collection
def get_random_string(length):
    # choose from all lowercase letter
    letters = string.ascii_lowercase
    result_str = "".join(random.choice(letters) for i in range(length))
    return result_str


# Pretty print objects in the response in a table format
def pp_objects(response, main_properties):

    # Create the header
    header = f"{'ID':<37}"
    for prop in main_properties:
        header += f"{prop.capitalize():<37}"
    header += f"{'Distance':<11}{'Certainty':<11}{'Score':<11}"
    print(header)

    objects = []
    if type(response) == weaviate.collections.classes.internal.ObjectSingleReturn:
        objects.append(response)
    else:
        objects = response.objects

    if len(objects) == 0:
        print("No objects found")
        return

    # Print each object
    for obj in objects:
        row = f"{str(obj.uuid):<36} "
        for prop in main_properties:
            row += f"{str(obj.properties.get(prop, ''))[:36]:<36} "
        row += f"{str(obj.metadata.distance)[:10] if hasattr(obj.metadata, 'distance') else 'None':<10} "
        row += f"{str(obj.metadata.certainty)[:10] if hasattr(obj.metadata, 'certainty') else 'None':<10} "
        row += f"{str(obj.metadata.score)[:10] if hasattr(obj.metadata, 'score') else 'None':<10}"
        print(row)

    # Print footer
    footer = f"{'':<37}" * (len(main_properties) + 1) + f"{'':<11}{'':<11}{'':<11}"
    print(footer)
    print(f"Total: {len(objects)} objects")


def parse_permission(perm: str) -> Union[RBAC.permissions, List[RBAC.permissions]]:
    """
    Convert a permission string to RBAC permission object(s).
    Format: action:collection[:tenant]

    Supports:
    - Basic permissions: read_schema:Movies
    - CRUD shorthand: crud_schema:Movies
    - Partial CRUD: cr_schema:Movies (create+read)
    - User management: manage_users
    - Role permissions: manage_roles, read_roles
    - Cluster permissions: read_cluster
    - Backup permissions: manage_backups
    - Schema permissions: create_schema, read_schema, update_schema, delete_schema
    - Data permissions: create_data, read_data, update_data, delete_data
    - Nodes permissions: read_nodes
    Args:
        perm (str): Permission string

    Returns:
        Union[RBAC.permissions, List[RBAC.permissions]]: Single permission or list for crud/partial crud
    """
    valid_resources = [
        "schema",
        "data",
        "roles",
        "users",
        "cluster",
        "backups",
        "nodes",
    ]
    parts = perm.split(":")
    if len(parts) > 3 or (parts[0] != "read_nodes" and len(parts) > 2):
        raise ValueError(
            f"Invalid permission format: {perm}. Expected format: action:collection/role/verbosity. Example: manage_roles:custom, crud_schema:Movies, read_nodes:verbose:Movies"
        )
    action = parts[0]
    role = parts[1] if len(parts) > 1 and "roles" in action else "*"
    verbosity = parts[1] if len(parts) > 1 and action == "read_nodes" else None
    if action == "read_nodes":
        # For read_nodes the first part belongs to the verbosity
        # and the second (optional) belongs to the collection
        # Example: read_nodes:verbose:Movies
        collection = parts[2] if len(parts) > 2 else "*"
    else:
        collection = (
            parts[1]
            if len(parts) > 1
            and action
            not in ["manage_roles", "manage_users", "read_roles", "read_cluster"]
            else "*"
        )

    # Handle standalone permissions first
    if action in ["manage_users", "read_cluster", "manage_backups", "read_nodes"]:
        return [
            _create_permission(
                action=action, collection=collection, verbosity=verbosity
            )
        ]

    out_permissions = []
    # Handle crud and partial crud cases
    if "_" in action:
        parts = action.split("_", 2)
        prefix = parts[0]
        resource = parts[1] if len(parts) > 1 else None
        if resource not in valid_resources:
            # Find closest matching resource type
            closest = min(
                valid_resources,
                key=lambda x: (
                    sum(c1 != c2 for c1, c2 in zip(x, resource))
                    if len(x) == len(resource)
                    else abs(len(x) - len(resource))
                ),
            )
            suggestion = f"\nDid you mean '{closest}'?" if closest else ""
            raise ValueError(f"Invalid resource type: {resource}. {suggestion}")

        action_map = {"c": "create", "r": "read", "u": "update", "d": "delete"}

        if prefix in ["create", "read", "update", "delete", "manage"]:
            actions = [prefix]
        else:
            # Handle partial crud (curd, cr, ru, ud, etc)
            if not all(c in action_map for c in prefix):
                raise ValueError(f"Invalid crud combination: {prefix}")
            actions = [action_map[c] for c in prefix]

        for act in actions:
            out_permissions.append(
                _create_permission(
                    action=f"{act}_{resource}",
                    role=role,
                    collection=collection,
                )
            )

        return out_permissions

    raise ValueError(f"Invalid permission action: {action}")


def _create_permission(
    action: str, role: str = "*", collection: str = "*", verbosity: str = "minimal"
) -> RBAC.permissions:
    """Helper function to create individual RBAC permission objects."""

    # Handle standalone permissions
    if action == "manage_users":
        return RBAC.permissions.users.manage()
    elif action == "read_cluster":
        return RBAC.permissions.cluster.read()
    elif action == "manage_backups":
        return RBAC.permissions.backups.manage(collection=collection)
    elif action == "read_nodes":
        return RBAC.permissions.nodes.read(verbosity=verbosity, collection=collection)
    # Handle roles permissions
    elif action in ["manage_roles", "read_roles"]:
        action_prefix = action.split("_")[0]  # will be either "manage" or "read"
        return getattr(RBAC.permissions.roles, action_prefix)(role=role)

    # Handle schema permissions
    elif action in [
        "create_schema",
        "read_schema",
        "update_schema",
        "delete_schema",
    ]:
        action_prefix = action.split("_")[0]
        return getattr(RBAC.permissions.config, action_prefix)(collection=collection)

    # Handle data permissions
    elif action in [
        "create_data",
        "read_data",
        "update_data",
        "delete_data",
    ]:
        action_prefix = action.split("_")[0]
        return getattr(RBAC.permissions.data, action_prefix)(collection=collection)

    raise ValueError(f"Invalid permission action: {action}.")
