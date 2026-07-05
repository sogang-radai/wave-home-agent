"""Tool layer: the only place agents may reach the C++ backend through.

Each module owns its own mock fixtures until the real C++ API is ready
(WAVEHOME_CORE_API_MOCK). Agents call these functions and never see HTTP.
"""
