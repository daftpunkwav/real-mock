"""Resume domain: upload, parse, list/activate/delete, and deep review.

HTTP surface for ``Resume`` rows in api.db (files live under the upload dir).
Interview and Prep must read picker / parsed profile through
``platform.services.resume_picker`` and ``platform.services.candidate_read``,
not by importing this package.

Public mount: ``router.service_router`` under ``/resume``.
"""
