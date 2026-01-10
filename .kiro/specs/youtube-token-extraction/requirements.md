# Requirements Document

## Introduction

This feature enhances the existing YouTube download service to bypass YouTube's advanced anti-bot measures (SABR protocol and PO Token validation) that cause yt-dlp to return 403 errors. The enhancement extends the current AgentGo browser automation to extract not only cookies but also PO Token and Visitor Data, then passes these tokens to yt-dlp for successful video downloads.

## Glossary

- **AgentGo_Service**: The browser automation service using Playwright to control remote browsers
- **PO_Token**: YouTube's proof-of-origin token used to validate legitimate browser requests
- **Visitor_Data**: YouTube's visitor identification data stored in browser configuration
- **yt-dlp**: The YouTube download library that requires authentication tokens
- **SABR_Protocol**: YouTube's anti-bot detection system requiring specific tokens
- **Network_Intercept**: Browser capability to monitor and capture network requests
- **Token_Extractor**: Component responsible for extracting authentication tokens from browser

## Requirements

### Requirement 1

**User Story:** As a system administrator, I want the YouTube download service to automatically extract PO tokens from browser sessions, so that downloads can bypass YouTube's anti-bot detection.

#### Acceptance Criteria

1. WHEN AgentGo_Service navigates to YouTube THEN the system SHALL monitor network requests for PO token parameters
2. WHEN a network request contains a "pot=" parameter THEN the Token_Extractor SHALL capture and parse the token value
3. WHEN PO token extraction fails THEN the system SHALL log a warning and continue with available authentication data
4. WHEN PO token is successfully extracted THEN the system SHALL format it as "web+{token}" for yt-dlp compatibility
5. WHEN multiple PO tokens are found THEN the system SHALL use the most recent valid token

### Requirement 2

**User Story:** As a system administrator, I want the YouTube download service to extract visitor data from browser sessions, so that the service can maintain consistent session identity.

#### Acceptance Criteria

1. WHEN AgentGo_Service loads a YouTube page THEN the system SHALL execute JavaScript to extract visitor data
2. WHEN visitor data extraction executes THEN the system SHALL attempt both window.ytcfg.get('VISITOR_DATA') and window.ytcfg.data_.VISITOR_DATA methods
3. WHEN visitor data is found THEN the system SHALL validate it is a non-empty string
4. WHEN visitor data extraction fails THEN the system SHALL log a warning and continue without visitor data
5. WHEN visitor data is successfully extracted THEN the system SHALL include it in the authentication bundle

### Requirement 3

**User Story:** As a system administrator, I want yt-dlp to use extracted tokens for authentication, so that video downloads can succeed despite YouTube's anti-bot measures.

#### Acceptance Criteria

1. WHEN the downloader receives authentication tokens THEN the system SHALL configure yt-dlp with extractor_args for YouTube
2. WHEN configuring yt-dlp THEN the system SHALL set player_client to 'web' to match token origin
3. WHEN PO token is available THEN the system SHALL add it to extractor_args with 'web+' prefix
4. WHEN visitor data is available THEN the system SHALL add it to extractor_args as visitor_data parameter
5. WHEN tokens are missing THEN the system SHALL fall back to cookie-only authentication

### Requirement 4

**User Story:** As a system administrator, I want the token extraction process to be robust and fault-tolerant, so that the service remains reliable even when token extraction fails.

#### Acceptance Criteria

1. WHEN token extraction encounters JavaScript errors THEN the system SHALL catch exceptions and continue processing
2. WHEN network interception fails THEN the system SHALL log the error and proceed with available data
3. WHEN token parsing fails THEN the system SHALL validate token format before usage
4. WHEN extraction timeout occurs THEN the system SHALL terminate gracefully after maximum wait time
5. WHEN all token extraction fails THEN the system SHALL fall back to existing cookie-based authentication

### Requirement 5

**User Story:** As a system administrator, I want comprehensive logging of token extraction activities, so that I can monitor and troubleshoot authentication issues.

#### Acceptance Criteria

1. WHEN token extraction begins THEN the system SHALL log the extraction attempt with timestamp
2. WHEN PO token is found THEN the system SHALL log successful extraction without exposing token value
3. WHEN visitor data is extracted THEN the system SHALL log the extraction success
4. WHEN extraction fails THEN the system SHALL log specific error details for debugging
5. WHEN tokens are passed to yt-dlp THEN the system SHALL log configuration without sensitive data