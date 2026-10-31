from .actions import ActionConfig, ActionMode, BatchActionConfig, ReturnEditsMode
from .client import OntologyClient, client_class
from .media import Media, MediaClient
from .objects import GeoPoint, LinkedObjects, Object, ObjectSet, ObjectType, Page, duration, max_group_count, metric
from .responses import (BatchApplyActionResponse, Record, SyncApplyActionResponse,
                        ValidateActionResponse)
from .where import Property, Where


def prop(name):
    """A property by wire name, for untyped where / order_by: ``prop("total") > 5``."""
    return Property(name)


__all__ = ["ActionConfig", "ActionMode", "BatchActionConfig", "BatchApplyActionResponse", "GeoPoint",
           "LinkedObjects", "Media", "MediaClient", "Object",
           "ObjectSet",
           "ObjectType", "OntologyClient", "Page", "Property", "Record", "ReturnEditsMode",
           "SyncApplyActionResponse", "ValidateActionResponse", "Where",
           "client_class", "duration", "max_group_count", "metric", "prop"]
