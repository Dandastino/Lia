-- Initialize Lia database schema
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Organizations table
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    connector_type VARCHAR(50) NOT NULL,
    connector_config JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Sync logs table
CREATE TABLE IF NOT EXISTS sync_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID REFERENCES organizations(id),
    status VARCHAR(50),
    target_system VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- User entity ownership (tracks which entities each user owns)
CREATE TABLE IF NOT EXISTS user_entity_ownership (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    entity_type VARCHAR(100) NOT NULL,
    external_entity_id VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, entity_type, external_entity_id)
);

-- External user mapping (maps LIA user UUIDs to external CRM user IDs)
CREATE TABLE IF NOT EXISTS external_user_mapping (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    crm_type VARCHAR(50) NOT NULL,
    external_user_id VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, crm_type)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_org_id ON users(org_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sync_logs_org_id ON sync_logs(org_id);
CREATE INDEX IF NOT EXISTS idx_sync_logs_created_at ON sync_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_user_entity_ownership_user_id ON user_entity_ownership(user_id);
CREATE INDEX IF NOT EXISTS idx_user_entity_ownership_org_id ON user_entity_ownership(org_id);
CREATE INDEX IF NOT EXISTS idx_user_entity_lookup ON user_entity_ownership(org_id, entity_type, external_entity_id);
CREATE INDEX IF NOT EXISTS idx_external_user_mapping_user_id ON external_user_mapping(user_id);
CREATE INDEX IF NOT EXISTS idx_external_user_mapping_org_id ON external_user_mapping(org_id);
CREATE INDEX IF NOT EXISTS idx_external_user_lookup ON external_user_mapping(org_id, crm_type, external_user_id);

INSERT INTO organizations (id, name, industry, connector_type, connector_config) VALUES 
  ('550e8400-e29b-41d4-a716-446655440001'::UUID, 'Lia Company', 'Technology', 'salesforce', '{"api_version": "v57"}')
ON CONFLICT DO NOTHING;

INSERT INTO users (org_id, email, password_hash, role, created_at) VALUES
  ('550e8400-e29b-41d4-a716-446655440001'::UUID, 'admin@lia.no', '$2b$12$2Pxac7KeyY1N92zKml228.MHBvA6Vg/TiHMS8wMuDFbHLB1IV8K7q', 'admin', CURRENT_TIMESTAMP)
ON CONFLICT DO NOTHING;
-- username: admin@lia.no - password : 4Dm1nL1A
