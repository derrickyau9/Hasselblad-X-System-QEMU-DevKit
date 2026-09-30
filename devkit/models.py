"""UI identities shared by the importer, launcher and workbench."""
MODELS = {
    'x1d': {'label': 'Hasselblad X1D 50C', 'abi': 'linux-arm32', 'hardware': '1.1.0'},
    'x1dii': {'label': 'Hasselblad X1D II 50C', 'abi': 'arm32', 'hardware': '12.1.0'},
    '907x50c': {'label': 'Hasselblad 907X / CFV II 50C', 'abi': 'arm32', 'hardware': '14.1.0'},
    'x2d': {'label': 'Hasselblad X2D 100C', 'abi': 'arm64', 'hardware': '4.1.0'},
    'x2dii': {'label': 'Hasselblad X2D II 100C', 'abi': 'arm64', 'hardware': '6.1.0'},
}

def model_id(profile):
    selected = profile.get('model')
    if selected in MODELS:
        return selected
    # Read libraries created by v0.1.1 without rewriting the user's data.
    name = profile.get('name', '')
    if name == 'Hasselblad X2D 100C': return 'x2d'
    if profile.get('abi') == 'linux-arm32': return 'x1d'
    if profile.get('abi') == 'arm32': return 'x1dii'
    return 'x2dii'

def available_models(profile):
    fallback = ['x1dii','907x50c'] if profile.get('sha256','').startswith('1bb69d26627d3af6') else [model_id(profile)]
    return [m for m in profile.get('available_models',fallback) if m in MODELS]
