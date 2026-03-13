# Firefly Corner tech Architecture - Agnes review - 11-13 March 2026 - Notes & Feedback
 

### System overview> FarmOS source of truth for:

ALL assets (not just plant and land assets). FarmOs ultimately needs to be the source of truth for all farm assets including structure assets, compost assets, equipment assets, water assets, seed assets and more. They might not be up to date TODAY but will be before we start effectively using them with AI 

ALL Logs  : and we should make use in full of farmOS logs capability including: log types (observation, activity, transplanting, seeding purchase, harvest, lab test, sale), log category, log owner, log status, log flags etc.

ALL taxonomy not just plant types

Users and roles / Authentication 

### System overview> Google sheet: 

Am weary of the sort term scalability of this, we could have loads of observation occurring at any point in time. Shall we have a cleanup task to delete rows for imported logs ? We know that of they are approved and imported the data is in farmOS. 

### Component Details > MCP Server - AI <-> farmOS Bridge >Tools:

Query_logs and import_observations : a small but quite beneficial update here would be to make sure that when the observation is approved, the entire content of the observation (including any associated photos which is part of the media component in roadmap) is in farmOS, including the name of the reported . The name of the reporter eventually could be linked to the real use

Query_logs and Get_inventory: does not seem to work as expected. Review the feedback from Claire’s Claude

missing tool: regenerate QR landing pages HTML. that is a big feedback from Claire when she has done the hard yakka to triage, approve and import the observations she really want to check in the field built right now her changes are not reflected in the HTML pages. I don’t want to be the bottleneck in that flow . There are no good reason to not have the page generated once farmOS is up to date . So let’s add this tool

### Component Details > MCP Server - AI <-> farmOS Bridge > Deployment:

Need to add a deployment for Olivier. He is the 4th partner on this initiative . He is the partner oc Alire and has been doing a lot of the operation on the farm . Especially the compost, work in the nursery and row management. He has a PC similar to Claire.

### Observation System — Field Data Capture:

We currently used the Firefly Agents Google workspace because we could not get the Firefly Corner workspace to work BUT i want to give it another try a the Firefly Corner Google workspace is really the right target. I changed the permission and some other aspects of the Firefly Corner account and admin user so i it might be working now . LEt’s give it a go

### Knowledge Base:

It is absolutely key that Claire can manage effectively the plant type taxonomy and that here changes are reflected in the plant type taxonomy in farmOS. I think this may need a dedicated flow and MCP tool 

Key principle: This key principle is ABSOLUTELY KEY: “All data flows INTO farmOS. Everything generated (pages, QR codes, reports) flows OUT of farmOS. farmOS is never bypassed.”

### Authentication & Access:

We need to add Olivier. Olivier already has a user in FarmOS with role Manager and will soon have a claude with farmOS MCP access

As already mentioned: need to move from Firefly Agents workspace to Firefly Corner workspace

Known Limitations> Single farmOS user:

That is not exactly true each local MCP uses a dedicated farmOS user to acces farmOS via MCP tools. Unless am missing something?

