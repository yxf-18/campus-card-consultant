USE campus_card_consultant;

CREATE TABLE IF NOT EXISTS merchant (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  category VARCHAR(30) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_merchant_name (name),
  KEY ix_merchant_category_name (category, name),
  CONSTRAINT ck_merchant_category CHECK (
    category IN ('食堂','超市','水电','网费','打印','洗衣','交通','补助','其他')
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS card_txn (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  card_no VARCHAR(64) NOT NULL,
  txn_time DATETIME NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  direction VARCHAR(8) NOT NULL,
  merchant_id BIGINT UNSIGNED NULL,
  channel VARCHAR(40) NULL,
  balance_after DECIMAL(12,2) NULL,
  summary VARCHAR(300) NULL,
  PRIMARY KEY (id),
  KEY ix_card_txn_card_time (card_no, txn_time),
  KEY ix_card_txn_merchant_time (merchant_id, txn_time),
  CONSTRAINT fk_txn_card FOREIGN KEY (card_no) REFERENCES campus_card_account(card_no),
  CONSTRAINT fk_txn_merchant FOREIGN KEY (merchant_id) REFERENCES merchant(id),
  CONSTRAINT ck_card_txn_direction CHECK (direction IN ('IN','OUT')),
  CONSTRAINT ck_card_txn_amount CHECK (amount >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS subsidy_record (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  card_no VARCHAR(64) NOT NULL,
  item VARCHAR(200) NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  pay_date DATE NOT NULL,
  source TEXT NULL,
  PRIMARY KEY (id),
  KEY ix_subsidy_card_date (card_no, pay_date),
  CONSTRAINT fk_subsidy_card FOREIGN KEY (card_no) REFERENCES campus_card_account(card_no),
  CONSTRAINT ck_subsidy_amount CHECK (amount >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS card_order (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_no VARCHAR(64) NOT NULL,
  card_no VARCHAR(64) NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  type VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'created',
  amount DECIMAL(12,2) NULL,
  payload_json JSON NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  remark VARCHAR(500) NULL,
  version INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_order_no (order_no),
  UNIQUE KEY uk_order_idempotency (idempotency_key),
  KEY ix_order_card_created (card_no, created_at),
  KEY ix_order_user_type_created (user_id, type, created_at),
  CONSTRAINT fk_order_card FOREIGN KEY (card_no) REFERENCES campus_card_account(card_no),
  CONSTRAINT fk_order_user FOREIGN KEY (user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_event (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_no VARCHAR(64) NOT NULL,
  from_status VARCHAR(20) NOT NULL,
  to_status VARCHAR(20) NOT NULL,
  at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  note VARCHAR(500) NULL,
  PRIMARY KEY (id),
  KEY ix_order_event_order_time (order_no, at),
  CONSTRAINT fk_event_order FOREIGN KEY (order_no) REFERENCES card_order(order_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS office (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(120) NOT NULL,
  address VARCHAR(250) NOT NULL,
  hours VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_office_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS appointment_slot (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  office_id BIGINT UNSIGNED NOT NULL,
  date DATE NOT NULL,
  slot VARCHAR(20) NOT NULL,
  capacity INT NOT NULL DEFAULT 20,
  booked INT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_slot_office_date_time (office_id, date, slot),
  KEY ix_slot_office_date (office_id, date, slot),
  CONSTRAINT fk_slot_office FOREIGN KEY (office_id) REFERENCES office(id),
  CONSTRAINT ck_slot_capacity CHECK (booked >= 0 AND booked <= capacity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS action_token (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  token VARCHAR(128) NOT NULL,
  card_no VARCHAR(64) NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  action_type VARCHAR(20) NOT NULL,
  params_hash VARCHAR(64) NOT NULL,
  params_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME NOT NULL,
  used TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uk_action_token (token),
  KEY ix_action_token_pending (user_id, card_no, used, expires_at),
  CONSTRAINT fk_action_token_card FOREIGN KEY (card_no) REFERENCES campus_card_account(card_no),
  CONSTRAINT fk_action_token_user FOREIGN KEY (user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
