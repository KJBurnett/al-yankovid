def test_personality_functions_nonempty():
    import personality
    funcs = ['get_ack', 'get_heavy_compression_quip', 'get_quip', 'get_error', 'get_top_user_quip', 'get_greeting']
    for fn in funcs:
        assert hasattr(personality, fn)
        val = getattr(personality, fn)()
        assert isinstance(val, str) and val.strip() != ''
