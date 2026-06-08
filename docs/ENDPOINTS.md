# GreyMatter MCP — Tool Catalog

Generated from the Postman collection. Do not edit by hand.

**Total operations:** 146

## Access Groups (`access_groups.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `access_group` | query | `accessGroup` |
| `access_groups` | query | `accessGroups` |
| `permissions` | query | `permissions` |
| `pod` | query | `pod` |
| `pods` | query | `pods` |
| `role` | query | `role` |
| `roles` | query | `roles` |
| `create_access_group` | mutation | `createAccessGroup` |
| `create_pod` | mutation | `createPod` |
| `create_role` | mutation | `createRole` |
| `delete_access_group` | mutation | `deleteAccessGroup` |
| `delete_pod` | mutation | `deletePod` |
| `delete_role` | mutation | `deleteRole` |
| `update_access_group` | mutation | `updateAccessGroup` |
| `update_pod` | mutation | `updatePod` |
| `update_role` | mutation | `updateRole` |

## API Keys (`api_keys.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `api_keys` | query | `apiKeys` |
| `create_api_key` | mutation | `createApiKey` |
| `delete_api_key_by_id` | mutation | `deleteApiKeyById` |
| `delete_api_keys` | mutation | `deleteApiKeys` |

## Assets (`assets.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `assets` | query | `assets` |
| `delete_asset` | mutation | `deleteAsset` |

## Cases (`cases.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `case` | query | `case` |
| `cases` | query | `cases` |
| `add_case_comment` | mutation | `addCaseComment` |
| `add_children_to_case` | mutation | `addChildrenToCase` |
| `cancel_case` | mutation | `cancelCase` |
| `close_case` | mutation | `closeCase` |
| `create_case` | mutation | `createCase` |
| `remove_child_from_case` | mutation | `removeChildFromCase` |
| `update_case` | mutation | `updateCase` |
| `update_case_due_date` | mutation | `updateCaseDueDate` |
| `update_case_owner` | mutation | `updateCaseOwner` |

## Customer (`customer.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `customer` | query | `customer` |
| `customers` | query | `customers` |

## Data (`data.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `data_source_schema` | query | `dataSourceSchema` |
| `time_buckets` | query | `timeBuckets` |

## Detections (`detections.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `customer_detection` | query | `customerDetection` |
| `customer_detection_activity_log_entries` | query | `customerDetectionActivityLogEntries` |
| `customer_detection_activity_log_entry` | query | `customerDetectionActivityLogEntry` |
| `customer_detections` | query | `customerDetections` |
| `detection_rules` | query | `detectionRules` |
| `draft_customer_detection` | query | `draftCustomerDetection` |
| `create_activity_log_entry_comment` | mutation | `createActivityLogEntryComment` |

## Discover Tasks (`discover_tasks.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `discover_task` | query | `discoverTask` |
| `discover_tasks` | query | `discoverTasks` |
| `assign_discover_task` | mutation | `assignDiscoverTask` |
| `close_discover_task` | mutation | `closeDiscoverTask` |
| `update_discover_task_state` | mutation | `updateDiscoverTaskState` |

## DRP Access Control (`drp_access_control.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `access_control_policies` | query | `accessControlPolicies` |
| `access_control_policy` | query | `accessControlPolicy` |
| `access_control_resources` | query | `accessControlResources` |
| `create_access_control_policy` | mutation | `createAccessControlPolicy` |
| `delete_access_control_policy` | mutation | `deleteAccessControlPolicy` |
| `update_access_control_policies` | mutation | `updateAccessControlPolicies` |
| `update_access_control_policy` | mutation | `updateAccessControlPolicy` |

## DRP Alerts (`drp_alerts.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `drp_alert` | query | `drpAlert` |
| `drp_alerts` | query | `drpAlerts` |
| `add_drp_alert_comment` | mutation | `addDrpAlertComment` |
| `assign_drp_alert` | mutation | `assignDRPAlert` |
| `assign_drp_alerts` | mutation | `assignDRPAlerts` |
| `bulk_add_drp_alert_comment` | mutation | `bulkAddDrpAlertComment` |
| `bulk_close_drp_alerts` | mutation | `bulkCloseDrpAlerts` |
| `bulk_update_drp_alert_state` | mutation | `bulkUpdateDrpAlertState` |
| `delete_drp_alert_comment` | mutation | `deleteDrpAlertComment` |
| `un_watch_drp_alert` | mutation | `unWatchDRPAlert` |
| `un_watch_drp_alerts` | mutation | `unWatchDRPAlerts` |
| `unassign_drp_alert` | mutation | `unassignDRPAlert` |
| `unassign_drp_alerts` | mutation | `unassignDRPAlerts` |
| `update_drp_alert_comment` | mutation | `updateDrpAlertComment` |
| `update_drp_alert_state` | mutation | `updateDrpAlertState` |
| `watch_drp_alert` | mutation | `watchDRPAlert` |
| `watch_drp_alerts` | mutation | `watchDRPAlerts` |

## Emergency Contacts (`emergency_contacts.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `emergency_contact` | query | `emergencyContact` |
| `emergency_contacts` | query | `emergencyContacts` |
| `create_emergency_contact` | mutation | `createEmergencyContact` |
| `delete_emergency_contact` | mutation | `deleteEmergencyContact` |
| `update_call_order` | mutation | `updateCallOrder` |
| `update_emergency_contact` | mutation | `updateEmergencyContact` |

## Fields (`fields.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `greymatter_field` | query | `greymatterField` |
| `greymatter_fields` | query | `greymatterFields` |

## Identities (`identities.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `identities` | query | `identities` |

## Incidents (`incidents.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `health_incidents` | query | `healthIncidents` |
| `incident` | query | `incident` |
| `incidents` | query | `incidents` |
| `acknowledge_assign_and_close_incident` | mutation | `acknowledgeAssignAndCloseIncident` |
| `acknowledge_incident` | mutation | `acknowledgeIncident` |
| `add_incident_comment` | mutation | `addIncidentComment` |
| `assign_incident` | mutation | `assignIncident` |
| `bulk_close_incidents` | mutation | `bulkCloseIncidents` |
| `close_incident` | mutation | `closeIncident` |
| `release_incident` | mutation | `releaseIncident` |
| `retain_incident` | mutation | `retainIncident` |
| `unresolve_incident` | mutation | `unresolveIncident` |
| `update_incident_state` | mutation | `updateIncidentState` |

## Indicators (`indicators.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `indicator` | query | `indicator` |
| `indicators` | query | `indicators` |

## Playbooks (`playbooks.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `customer_playbooks` | query | `customerPlaybooks` |
| `playbook_run` | query | `playbookRun` |
| `playbook_run_filter_data` | query | `playbookRunFilterData` |
| `playbook_runs` | query | `playbookRuns` |
| `playbooks` | query | `playbooks` |
| `recommended_playbooks` | query | `recommendedPlaybooks` |
| `rerun_all_failed_tasks_for_playbook_run` | mutation | `rerunAllFailedTasksForPlaybookRun` |
| `run_playbook` | mutation | `runPlaybook` |
| `upsert_customer_playbook` | mutation | `upsertCustomerPlaybook` |
| `upsert_playbook_metadata` | mutation | `upsertPlaybookMetadata` |

## Query Management (`query_management.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `integration` | query | `integration` |
| `integrations` | query | `integrations` |
| `search_history` | query | `searchHistory` |

## Reference Lists (`reference_lists.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `reference_list` | query | `referenceList` |
| `reference_lists` | query | `referenceLists` |
| `create_reference_list` | mutation | `createReferenceList` |
| `create_reference_list_column` | mutation | `createReferenceListColumn` |
| `create_reference_list_row` | mutation | `createReferenceListRow` |
| `delete_reference_list` | mutation | `deleteReferenceList` |
| `delete_reference_list_column` | mutation | `deleteReferenceListColumn` |
| `delete_reference_list_row` | mutation | `deleteReferenceListRow` |
| `update_reference_list` | mutation | `updateReferenceList` |
| `update_reference_list_column` | mutation | `updateReferenceListColumn` |
| `update_reference_list_row` | mutation | `updateReferenceListRow` |

## Tasks (`tasks.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `task` | query | `task` |
| `tasks` | query | `tasks` |
| `acknowledge_task` | mutation | `acknowledgeTask` |
| `add_task_comment` | mutation | `addTaskComment` |
| `assign_task` | mutation | `assignTask` |
| `bulk_resolve_tasks` | mutation | `bulkResolveTasks` |
| `create_task` | mutation | `createTask` |
| `resolve_task` | mutation | `resolveTask` |
| `unresolve_task` | mutation | `unresolveTask` |
| `update_task_retained_status` | mutation | `updateTaskRetainedStatus` |
| `update_task_state` | mutation | `updateTaskState` |

## User (`user.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `me` | query | `me` |
| `user` | query | `user` |
| `create_user` | mutation | `createUser` |
| `delete_user` | mutation | `deleteUser` |
| `disable_user` | mutation | `disableUser` |
| `enable_user` | mutation | `enableUser` |
| `generate_password_link` | mutation | `generatePasswordLink` |
| `resend_invite` | mutation | `resendInvite` |
| `reset_mfa` | mutation | `resetMfa` |
| `send_forgot_password` | mutation | `sendForgotPassword` |
| `update_user` | mutation | `updateUser` |

## User Activity (`user_activity.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `audits` | query | `audits` |

## Utilities (`utilities.py`)

| Tool | Kind | GraphQL operation |
|---|---|---|
| `node` | query | `node` |
| `rate_limit` | query | `rateLimit` |
