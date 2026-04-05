-- Test data for Temporal workflow testing

-- Insert test agent
INSERT INTO public.agent (agent_id, agent_name, agent_type, agent_status, api_key, config, capabilities)
VALUES (
    1,
    'Test Agent',
    '1',
    'ACTIVE',
    'test_api_key_123',
    '{"responsibilities": "Test responsibilities", "constraints": "Test constraints", "success_criteria": "Test success"}'::jsonb,
    '{}'::jsonb
)
ON CONFLICT DO NOTHING;

-- Insert test project
INSERT INTO public.project (project_id, project_name, project_type, status)
VALUES (1, 'Test Project', 'TEST', 'ACTIVE')
ON CONFLICT DO NOTHING;

-- Insert test document
INSERT INTO public.project_document (
    project_id,
    document_name,
    document_type,
    raw_text_content,
    is_active_version
)
VALUES (
    1,
    'Test Document',
    'TEXT',
    'This is a test document for the Temporal workflow. It contains some sample text that will be chunked and embedded. The document has multiple sentences to test the chunking functionality. We want to see how the RAG system processes this content. This is another paragraph with more content to ensure we have enough text for meaningful chunking.',
    TRUE
);

