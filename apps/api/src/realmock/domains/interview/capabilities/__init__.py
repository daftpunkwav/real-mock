"""Mock interview domain capability layer (interview-specific capabilities moved down from platform).

Currently includes enterprise knowledge-base RAG (``rag``). This capability is consumed only by ``realmock.domains.interview``,
so it physically belongs to this service; platform capabilities shared by all three services remain in ``realmock.platform.capabilities``.
"""
