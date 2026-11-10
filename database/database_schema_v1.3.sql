CREATE DATABASE IF NOT EXISTS campus_card_consultant
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE campus_card_consultant;

CREATE TABLE IF NOT EXISTS sys_user (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(50) NOT NULL,
  phone VARCHAR(20) NULL,
  email VARCHAR(100) NULL,
  student_no VARCHAR(50) NULL,
  password_hash VARCHAR(255) NOT NULL,
  nickname VARCHAR(50) NOT NULL,
  role ENUM('USER','ADMIN') NOT NULL DEFAULT 'USER',
  status ENUM('ACTIVE','DISABLED') NOT NULL DEFAULT 'ACTIVE',
  failed_login_count INT UNSIGNED NOT NULL DEFAULT 0,
  locked_until DATETIME NULL,
  privacy_agreed_at DATETIME NULL,
  last_login_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_username (username),
  UNIQUE KEY uk_user_phone (phone),
  UNIQUE KEY uk_user_email (email),
  UNIQUE KEY uk_user_student_no (student_no),
  KEY ix_user_role_status (role, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sys_config (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  config_key VARCHAR(100) NOT NULL,
  config_group VARCHAR(50) NOT NULL DEFAULT 'general',
  config_value LONGTEXT NULL,
  value_type ENUM('STRING','INT','BOOL','JSON') NOT NULL DEFAULT 'STRING',
  description VARCHAR(255) NULL,
  updated_by BIGINT UNSIGNED NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_config_key (config_key),
  CONSTRAINT fk_config_user FOREIGN KEY (updated_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS campus_card_account (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  card_no VARCHAR(64) NOT NULL,
  balance DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  status ENUM('ACTIVE','FROZEN','CLOSED') NOT NULL DEFAULT 'ACTIVE',
  last_transaction_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_card_user (user_id),
  UNIQUE KEY uk_card_no (card_no),
  KEY ix_card_status (status),
  CONSTRAINT fk_card_user FOREIGN KEY (user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS knowledge_category (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(50) NOT NULL,
  default_cover_url VARCHAR(500) NULL,
  sort_order INT NOT NULL DEFAULT 0,
  status ENUM('ENABLED','DISABLED') NOT NULL DEFAULT 'ENABLED',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_category_name (name),
  KEY ix_category_status_sort (status, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS knowledge_document (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  category_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(200) NOT NULL,
  summary VARCHAR(500) NULL,
  keywords VARCHAR(500) NULL,
  cover_url VARCHAR(500) NULL,
  file_name VARCHAR(255) NOT NULL,
  storage_path VARCHAR(500) NOT NULL,
  parsed_text LONGTEXT NULL,
  file_type VARCHAR(20) NOT NULL,
  file_size BIGINT UNSIGNED NOT NULL DEFAULT 0,
  file_hash CHAR(64) NULL,
  source_department VARCHAR(200) NULL,
  document_no VARCHAR(100) NULL,
  effective_date DATE NULL,
  expire_date DATE NULL,
  status ENUM('DRAFT','PUBLISHED','OFFLINE','EXPIRED') NOT NULL DEFAULT 'DRAFT',
  sync_status ENUM('NOT_INDEXED','PENDING','RUNNING','SUCCESS','FAILED') NOT NULL DEFAULT 'NOT_INDEXED',
  active_index_version INT UNSIGNED NOT NULL DEFAULT 0,
  view_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
  sort_order INT NOT NULL DEFAULT 0,
  allow_download TINYINT(1) NOT NULL DEFAULT 1,
  published_at DATETIME NULL,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NOT NULL,
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  deleted_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_document_category_status (category_id, status, is_deleted),
  KEY ix_document_expire (expire_date),
  KEY ix_document_sync (sync_status),
  FULLTEXT KEY ft_document_search (title, summary, keywords),
  CONSTRAINT fk_document_category FOREIGN KEY (category_id) REFERENCES knowledge_category(id),
  CONSTRAINT fk_document_created_by FOREIGN KEY (created_by) REFERENCES sys_user(id),
  CONSTRAINT fk_document_updated_by FOREIGN KEY (updated_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS knowledge_chunk (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_id BIGINT UNSIGNED NOT NULL,
  version_no INT UNSIGNED NOT NULL DEFAULT 1,
  chunk_index INT UNSIGNED NOT NULL,
  heading_path VARCHAR(500) NULL,
  page_no INT UNSIGNED NULL,
  content MEDIUMTEXT NOT NULL,
  char_count INT UNSIGNED NOT NULL,
  vector_id VARCHAR(128) NULL,
  embedding_model VARCHAR(100) NULL,
  chunk_status ENUM('PENDING','ACTIVE','INACTIVE') NOT NULL DEFAULT 'PENDING',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_chunk_vector (vector_id),
  UNIQUE KEY uq_chunk_doc_version_index (document_id, version_no, chunk_index),
  KEY ix_chunk_document_status (document_id, chunk_status),
  CONSTRAINT fk_chunk_document FOREIGN KEY (document_id) REFERENCES knowledge_document(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS rag_sync_task (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_id BIGINT UNSIGNED NOT NULL,
  task_type ENUM('CREATE','UPDATE','OFFLINE','DELETE','REINDEX') NOT NULL,
  target_version INT UNSIGNED NOT NULL DEFAULT 1,
  status ENUM('PENDING','RUNNING','SUCCESS','FAILED') NOT NULL DEFAULT 'PENDING',
  retry_count INT UNSIGNED NOT NULL DEFAULT 0,
  chunk_count INT UNSIGNED NULL,
  duration_ms INT UNSIGNED NULL,
  error_message VARCHAR(1000) NULL,
  created_by BIGINT UNSIGNED NULL,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_sync_document_status (document_id, status),
  KEY ix_sync_status_created (status, created_at),
  CONSTRAINT fk_sync_document FOREIGN KEY (document_id) REFERENCES knowledge_document(id),
  CONSTRAINT fk_sync_created_by FOREIGN KEY (created_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS chat_session (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(200) NOT NULL,
  context_summary TEXT NULL,
  status ENUM('ACTIVE','DELETED') NOT NULL DEFAULT 'ACTIVE',
  last_message_at DATETIME NULL,
  deleted_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_session_user_status_last (user_id, status, last_message_at),
  CONSTRAINT fk_session_user FOREIGN KEY (user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS chat_message (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  session_id BIGINT UNSIGNED NOT NULL,
  role ENUM('USER','ASSISTANT') NOT NULL,
  reply_to_message_id BIGINT UNSIGNED NULL,
  content LONGTEXT NOT NULL,
  status ENUM('SUCCESS','FAILED') NOT NULL DEFAULT 'SUCCESS',
  model_name VARCHAR(100) NULL,
  prompt_tokens INT UNSIGNED NULL,
  completion_tokens INT UNSIGNED NULL,
  latency_ms INT UNSIGNED NULL,
  is_grounded TINYINT(1) NOT NULL DEFAULT 1,
  suggestions JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_message_session_created (session_id, created_at),
  KEY ix_message_reply_to (reply_to_message_id),
  KEY ix_message_role_status (role, status),
  CONSTRAINT fk_message_session FOREIGN KEY (session_id) REFERENCES chat_session(id),
  CONSTRAINT fk_message_reply FOREIGN KEY (reply_to_message_id) REFERENCES chat_message(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS chat_citation (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  message_id BIGINT UNSIGNED NOT NULL,
  source_type ENUM('DOCUMENT','WEB','TOOL') NOT NULL,
  document_id BIGINT UNSIGNED NULL,
  chunk_id BIGINT UNSIGNED NULL,
  title VARCHAR(300) NOT NULL,
  source_url VARCHAR(1000) NULL,
  snippet TEXT NULL,
  page_no INT UNSIGNED NULL,
  tool_name VARCHAR(100) NULL,
  sort_order INT UNSIGNED NOT NULL DEFAULT 0,
  retrieved_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_citation_message_order (message_id, sort_order),
  KEY ix_citation_document (document_id),
  KEY ix_citation_chunk (chunk_id),
  CONSTRAINT fk_citation_message FOREIGN KEY (message_id) REFERENCES chat_message(id),
  CONSTRAINT fk_citation_document FOREIGN KEY (document_id) REFERENCES knowledge_document(id),
  CONSTRAINT fk_citation_chunk FOREIGN KEY (chunk_id) REFERENCES knowledge_chunk(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS chat_feedback (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  message_id BIGINT UNSIGNED NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  rating ENUM('LIKE','DISLIKE') NOT NULL,
  reason VARCHAR(500) NULL,
  status ENUM('PENDING','PROCESSED','IGNORED') NOT NULL DEFAULT 'PENDING',
  handled_by BIGINT UNSIGNED NULL,
  handled_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_feedback_message_user (message_id, user_id),
  KEY ix_feedback_status_created (status, created_at),
  CONSTRAINT fk_feedback_message FOREIGN KEY (message_id) REFERENCES chat_message(id),
  CONSTRAINT fk_feedback_user FOREIGN KEY (user_id) REFERENCES sys_user(id),
  CONSTRAINT fk_feedback_handled_by FOREIGN KEY (handled_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS profile_change_request (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  field_name ENUM('phone','email') NOT NULL,
  old_value VARCHAR(100) NULL,
  new_value VARCHAR(100) NOT NULL,
  status ENUM('PENDING','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING',
  remark VARCHAR(500) NULL,
  reviewed_by BIGINT UNSIGNED NULL,
  reviewed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_profile_change_status_created (status, created_at),
  KEY ix_profile_change_user_field (user_id, field_name, status),
  CONSTRAINT fk_profile_change_user FOREIGN KEY (user_id) REFERENCES sys_user(id),
  CONSTRAINT fk_profile_change_reviewer FOREIGN KEY (reviewed_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
