import uuid

import inngest
from loguru import logger
from sqlmodel import Session

from hypersmell.database import engine
from hypersmell.integrations.supplier_catalog import SupplierCatalogIntegration
from hypersmell.integrations.tasting_notes import TastingNotesIntegration
from hypersmell.models import Connection, Resource
from hypersmell.pipeline.orchestrator import process_resource
from hypersmell.settings import get_settings
from hypersmell.tasks.client import client
from hypersmell.tasks.events import Events


@client.create_function(
    fn_id="sync-integration",
    trigger=inngest.TriggerEvent(event=Events.SYNC_INTEGRATION),
)
def sync_integration(ctx: inngest.Context, step: inngest.Step):
    """Sync all resources from an integration."""
    workspace_id = uuid.UUID(ctx.event.data["workspace_id"])
    integration_name = ctx.event.data["integration"]

    settings = get_settings()

    with Session(engine) as session:
        connection = session.query(Connection).filter(
            Connection.workspace_id == workspace_id,
            Connection.integration == integration_name,
        ).first()

        if not connection:
            logger.error(f"No connection found for {integration_name}")
            return

        # Resolve integration class
        if integration_name == "supplier_catalog":
            integration = SupplierCatalogIntegration(connection, settings)
        elif integration_name == "tasting_notes":
            integration = TastingNotesIntegration(connection, settings)
        else:
            logger.error(f"Unknown integration: {integration_name}")
            return

        resources = integration.list_all_resources()
        logger.info(f"Found {len(resources)} resources to sync")

        for resource_data in resources:
            # Create or update resource record
            existing = session.query(Resource).filter(
                Resource.workspace_id == workspace_id,
                Resource.integration == integration_name,
                Resource.external_id == resource_data["id"],
            ).first()

            if not existing:
                resource = Resource(
                    workspace_id=workspace_id,
                    integration=integration_name,
                    external_id=resource_data["id"],
                    title=resource_data.get("name", ""),
                    status="pending",
                )
                session.add(resource)
                session.commit()
                session.refresh(resource)

                # Send process event
                step.send_event(
                    f"process-{resource.id}",
                    inngest.Event(
                        name=Events.PROCESS_RESOURCE,
                        data={
                            "resource_id": str(resource.id),
                            "workspace_id": str(workspace_id),
                            "integration": integration_name,
                        },
                    ),
                )


@client.create_function(
    fn_id="process-resource",
    trigger=inngest.TriggerEvent(event=Events.PROCESS_RESOURCE),
)
def fn_process_resource(ctx: inngest.Context, step: inngest.Step):
    """Fetch and process a single resource through the pipeline."""
    resource_id = uuid.UUID(ctx.event.data["resource_id"])
    integration_name = ctx.event.data["integration"]

    settings = get_settings()

    with Session(engine) as session:
        resource = session.get(Resource, resource_id)
        if not resource:
            logger.error(f"Resource {resource_id} not found")
            return

        connection = session.query(Connection).filter(
            Connection.workspace_id == resource.workspace_id,
            Connection.integration == integration_name,
        ).first()

        if integration_name == "supplier_catalog":
            integration = SupplierCatalogIntegration(connection, settings)
        elif integration_name == "tasting_notes":
            integration = TastingNotesIntegration(connection, settings)
        else:
            logger.error(f"Unknown integration: {integration_name}")
            return

        # Fetch full content
        data = integration.fetch_resource(resource.external_id)
        resource.content = data["content"]
        resource.title = data["title"]
        resource.doc_metadata = data.get("metadata", {})
        session.add(resource)
        session.commit()

        # Run pipeline
        process_resource(session, resource, settings.embedding_model)
