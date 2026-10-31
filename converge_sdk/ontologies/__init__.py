from .actions import ActionConfig, ActionMode, BatchActionConfig, ReturnEditsMode
from .client import OntologyClient, client_class
from .media import Media, MediaClient
from .objects import LinkedObjects, Object, ObjectSet, ObjectType, Page
from .where import Property, Where


def prop(name):
    """A property by wire name, for untyped where / order_by: ``prop("total") > 5``."""
    return Property(name)


__all__ = ["ActionConfig", "ActionMode", "BatchActionConfig", "LinkedObjects", "Media", "MediaClient", "Object",
           "ObjectSet",
           "ObjectType", "OntologyClient", "Page", "Property", "ReturnEditsMode", "Where",
           "client_class", "prop"]
