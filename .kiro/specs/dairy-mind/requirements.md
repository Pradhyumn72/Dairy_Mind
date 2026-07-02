# Requirements Document

## Introduction

DairyMind is a Smart Dairy Farm Management System — a full-stack web application built with Django 4.2 + Django REST Framework (backend), MySQL 8.0 (database), Bootstrap 5 + Chart.js + vanilla JS (frontend), Celery + Redis (task queue), Scikit-learn + Facebook Prophet (ML/forecasting), and Google Gemini API (LLM-based document summarization).

The system centralizes cattle registry management, milk production tracking, health monitoring, AI-driven forecasting, veterinary document analysis, feed cost optimization, and breeding lifecycle management for dairy farm operators.

---

## Glossary

- **System**: The DairyMind application as a whole
- **Cattle_Registry**: The module responsible for storing and managing individual animal records
- **Animal**: A single dairy animal identified by a unique tag number within the system
- **Milk_Tracker**: The module responsible for recording and displaying daily milk production logs
- **Milk_Log**: A single daily production record linking an Animal, a date, and a volume in liters
- **Health_Alert_Engine**: The Scikit-learn-based anomaly detection component that identifies abnormal milk production drops
- **Alert**: A system-generated notification indicating a potential health or production issue for a specific Animal
- **Forecast_Engine**: The Facebook Prophet-based component that generates 30-day milk yield forecasts
- **Forecast**: A time-series prediction record for a given Animal or herd covering a future 30-day window
- **Vet_Report_Summarizer**: The Google Gemini API integration component that processes veterinary documents
- **Vet_Report**: An uploaded PDF or plain-text veterinary document associated with an Animal
- **Cost_Optimizer**: The module that calculates feed cost versus milk yield return-on-investment
- **ROI_Record**: A calculated record linking feed cost inputs to milk yield outputs and a computed ROI ratio
- **Breeding_Manager**: The module that tracks reproductive events and predicts optimal breeding dates
- **Heat_Cycle**: A recorded estrus event for a female Animal with a start date
- **Pregnancy**: A recorded gestation event for a female Animal with an expected calving date
- **AI_Event**: An artificial insemination event associated with a female Animal and a Bull_Code
- **Bull_Code**: An identifier for the semen sample used in an AI_Event
- **Breeding_Prediction**: A system-generated recommendation for the optimal next breeding date and estimated success probability
- **Celery_Worker**: The background task processing component powered by Celery and Redis
- **Farm_User**: An authenticated user of the system with a role of Admin, Farm_Manager, or Vet
- **Dashboard**: The main landing page after login, displaying aggregated farm statistics and alerts
- **REST_API**: The Django REST Framework-based HTTP interface consumed by the frontend

---

## Requirements

---

### Requirement 1: User Authentication and Role-Based Access Control

**User Story:** As a Farm_User, I want to log in with credentials and be assigned a role, so that I can access only the features appropriate for my responsibilities.

#### Acceptance Criteria

1. THE System SHALL require a Farm_User to authenticate with a username and password before accessing any protected resource.
2. WHEN a Farm_User submits valid credentials, THE System SHALL issue a session token and redirect the Farm_User to the Dashboard.
3. IF a Farm_User submits invalid credentials, THEN THE System SHALL return an error response with HTTP status 401 and a descriptive message, without revealing which field was incorrect.
4. THE System SHALL assign each Farm_User exactly one role from the set {Admin, Farm_Manager, Vet}.
5. WHILE a Farm_User holds the Vet role, THE System SHALL grant create, update, and delete access to the Vet_Report and Health_Alert modules, and restrict create, update, and delete access to all other modules.
6. WHILE a Farm_User holds the Farm_Manager role, THE System SHALL grant read and write access to Cattle_Registry, Milk_Tracker, Cost_Optimizer, and Breeding_Manager, and read-only access to Vet_Report summaries.
7. WHILE a Farm_User holds the Admin role, THE System SHALL grant full read and write access to all modules and to Farm_User management, where Farm_User management includes creating, updating, and deactivating Farm_User accounts and assigning roles.
8. IF a Farm_User makes no authenticated request for 8 consecutive hours, THEN THE System SHALL invalidate that Farm_User's session token and require re-authentication on the next request.
9. IF a Farm_User attempts to access a resource outside the permissions of their assigned role, THEN THE System SHALL return HTTP status 403 with an error message indicating insufficient permissions.
10. IF a Farm_User submits 5 consecutive failed login attempts within a 15-minute window, THEN THE System SHALL lock that account for 30 minutes and return HTTP status 429 with a message indicating the lockout duration.

---

### Requirement 2: Cattle Registry — Animal CRUD and History Tracking

**User Story:** As a Farm_Manager, I want to create, view, update, and delete animal records with full history, so that I can maintain an accurate and auditable register of every animal on the farm.

#### Acceptance Criteria

1. THE Cattle_Registry SHALL store the following mandatory fields for each Animal: tag_number (1–20 alphanumeric characters, unique), name (1–100 characters), breed (1–100 characters), date_of_birth (valid calendar date, not in the future), gender (one of {Male, Female}), and status (one of {Active, Dry, Sold, Deceased}).
2. THE Cattle_Registry SHALL store the following optional fields for each Animal: sire_tag, dam_tag, purchase_date, and notes (maximum 1000 characters).
3. WHEN a Farm_Manager creates an Animal record, THE Cattle_Registry SHALL validate that the tag_number is unique across all Animal records and that all mandatory field constraints are satisfied before persisting.
4. IF a duplicate tag_number is submitted during Animal creation, THEN THE Cattle_Registry SHALL reject the request with a validation error identifying the conflicting tag_number.
5. IF any mandatory field violates its defined constraint on create or update, THEN THE Cattle_Registry SHALL reject the request with a field-level validation error identifying each invalid field.
6. WHEN a Farm_Manager creates, updates, or deletes an Animal record, THE Cattle_Registry SHALL persist a versioned history entry recording the action type (created, updated, deleted), the previous field values, the changed fields, the timestamp, and the Farm_User who performed the action.
7. WHEN a Farm_Manager submits a search query of 1–100 characters, THE Cattle_Registry SHALL return Animals matching by tag_number, name, breed, or status using case-insensitive partial matching.
8. WHEN a Farm_Manager sets an Animal's status to Deceased or Sold, THE Cattle_Registry SHALL mark that Animal as inactive, retain all historical records, and exclude the Animal from default active-Animal list results.
9. WHEN a Farm_Manager deletes an Animal record, THE Cattle_Registry SHALL perform a soft-delete that sets the Animal to inactive, retains all associated Milk_Log, Alert, and Breeding records, and excludes the Animal from default list results while allowing retrieval via an explicit deleted=true filter.
10. WHEN a Farm_Manager requests the Animal list, THE REST_API SHALL return a paginated response with a default page size of 20 and a maximum page size of 100, including a total count of matching records.
11. WHEN a Farm_Manager views an Animal detail page, THE Cattle_Registry SHALL display that Animal's full version history ordered from most recent to oldest, with each entry showing the action type, changed fields, previous values, timestamp, and the Farm_User who made the change.

---

### Requirement 3: Milk Tracker — Daily Production Logging and Trend Visualization

**User Story:** As a Farm_Manager, I want to log daily milk production per animal and view trend charts, so that I can monitor individual and herd-level output over time.

#### Acceptance Criteria

1. WHEN a Farm_Manager creates a Milk_Log, THE Milk_Tracker SHALL require animal_tag, date, morning_yield_liters (≥ 0, numeric), and evening_yield_liters (≥ 0, numeric), and accept an optional notes field of up to 500 characters.
2. WHEN a Milk_Log is persisted, THE Milk_Tracker SHALL compute and store total_daily_yield_liters as the sum of morning_yield_liters and evening_yield_liters.
3. IF a Farm_Manager submits a Milk_Log with a date and animal_tag combination that already exists, THEN THE Milk_Tracker SHALL reject the request with a validation error identifying the duplicate combination.
4. IF morning_yield_liters or evening_yield_liters is submitted as a negative number or a non-numeric value, THEN THE Milk_Tracker SHALL return HTTP status 400 with a field-level validation error identifying the offending field.
5. WHEN a Farm_Manager requests the herd summary for a given date range, THE Milk_Tracker SHALL return daily total_daily_yield_liters aggregated across all active Animals for each date in the range, in ascending date order, in a format suitable for Chart.js consumption.
6. WHEN a Farm_Manager requests per-Animal yield data, THE Milk_Tracker SHALL return that Animal's daily yield time series for a configurable date range up to 365 days, in ascending date order.
7. WHEN the Dashboard page loads, THE System SHALL display a Chart.js line chart showing the herd's total daily milk yield for the trailing 30 calendar days from the current date.
8. WHEN a Farm_Manager views an Animal detail page, THE System SHALL display a Chart.js line chart showing that Animal's daily total yield for the trailing 90 calendar days from the current date.
9. WHEN a Farm_Manager submits a bulk creation request, THE Milk_Tracker SHALL accept up to 100 Milk_Log entries in a single request, validate each entry independently, and return a response indicating the count of successfully created entries and a list of validation errors for any rejected entries.

---

### Requirement 4: Health Alerts — Anomaly Detection on Milk Production

**User Story:** As a Farm_Manager, I want to receive automated alerts when an animal's milk production drops abnormally, so that I can investigate potential health issues early.

#### Acceptance Criteria

1. THE Health_Alert_Engine SHALL use an Isolation Forest model trained on each Animal's historical Milk_Log data to classify daily yield values as normal or anomalous.
2. WHEN a new Milk_Log is saved for an Animal, THE Health_Alert_Engine SHALL evaluate the new yield value against the trained model for that Animal within 5 minutes of the save event.
3. IF the Health_Alert_Engine classifies a yield value as anomalous, THEN THE System SHALL create an Alert record where: observed_yield matches the Milk_Log total_daily_yield_liters (in liters), expected_range lower bound is less than or equal to the upper bound (in liters), and severity is assigned as Low when observed_yield deviates less than 20% below expected_range lower bound, Medium when it deviates 20%–40%, and High when it deviates more than 40%.
4. THE Celery_Worker SHALL execute the anomaly detection task asynchronously to avoid blocking the Milk_Log save response.
5. WHEN an Alert is created, THE System SHALL deliver a notification to all Farm_Manager and Admin Farm_Users via the Dashboard notification panel within 5 minutes of Alert creation. IF notification delivery fails for any Farm_User, THE System SHALL retain the Alert record and log the delivery failure at ERROR severity.
6. THE Health_Alert_Engine SHALL require a minimum of 30 historical Milk_Log records for an Animal before evaluating anomalies, to ensure model reliability.
7. IF an Animal has fewer than 30 historical Milk_Log records, THEN THE System SHALL skip anomaly evaluation for that Animal and log a debug message.
8. THE System SHALL expose a REST_API endpoint returning all Alerts filterable by animal_tag, severity, date range, and acknowledgement status.
9. WHEN a Farm_Manager acknowledges an Alert that has not previously been acknowledged, THE System SHALL record the acknowledging Farm_User and timestamp on the Alert record. IF the Alert has already been acknowledged, THEN THE System SHALL reject the request with a validation error indicating the Alert is already acknowledged.
10. WHEN an Animal accumulates 50 new Milk_Log records since the last model training, THE Health_Alert_Engine SHALL retrain the Isolation Forest model for that Animal via the Celery_Worker. IF retraining fails, THE System SHALL retain the previous model version and log the failure at ERROR severity.

---

### Requirement 5: Production Forecast — 30-Day Milk Yield Prediction

**User Story:** As a Farm_Manager, I want to see a 30-day milk production forecast for the herd and individual animals, so that I can plan feed procurement and staffing in advance.

#### Acceptance Criteria

1. WHEN the Forecast_Engine generates a Forecast for an Animal, it SHALL use the Facebook Prophet library and require at least 60 historical Milk_Log records for that Animal.
2. WHEN a Farm_Manager requests a Forecast for an Animal, THE Forecast_Engine SHALL return daily predicted yield values with upper and lower confidence interval bounds for each of the 30 forecast days, where predicted yield values of zero are accepted as valid predictions.
3. WHEN a herd-level Forecast is requested, THE Forecast_Engine SHALL generate it by aggregating per-Animal daily predictions for all active Animals on the farm.
4. WHEN the Celery_Worker executes the nightly scheduled task at 02:00 server time, THE Forecast_Engine SHALL regenerate Forecasts for all eligible Animals using the latest available Milk_Log data.
5. IF an Animal has fewer than 60 historical Milk_Log records, THEN THE Forecast_Engine SHALL return a response indicating insufficient data rather than returning an unreliable Forecast.
6. WHEN a Farm_Manager views the forecast page, THE System SHALL render a Chart.js line chart displaying the 30 most recent days of observed historical yield alongside the 30-day predicted series with upper and lower confidence bands.
7. THE REST_API SHALL expose an endpoint returning a Forecast for a given Animal or for the full herd, including predicted_date, predicted_yield, lower_bound, and upper_bound fields for each forecast day.
8. WHEN the Forecast_Engine completes a Forecast generation, THE System SHALL overwrite the previous stored Forecast results for the same Animal or herd in the database so that retrieval returns the most recent Forecast without recomputation.
9. WHEN a Farm_Manager triggers a manual Forecast refresh via the UI, THE Celery_Worker SHALL enqueue the Forecast generation task and return a task status identifier with status one of {pending, in_progress, completed, failed} to the Farm_Manager.
10. IF a stored Forecast for an Animal or the herd is older than 24 hours at the time of retrieval, THEN THE System SHALL include a staleness warning in the response indicating the Forecast may not reflect the latest data.

---

### Requirement 6: Vet Report AI Summarizer

**User Story:** As a Vet, I want to upload a veterinary report and receive a plain-English summary, so that Farm_Managers can quickly understand medical findings without veterinary training.

#### Acceptance Criteria

1. THE Vet_Report_Summarizer SHALL accept PDF (MIME type application/pdf) and plain-text (MIME type text/plain) file uploads associated with a specific Animal.
2. WHEN a Vet uploads a Vet_Report file, THE System SHALL store the original file in a designated media directory, create a Vet_Report database record linking the file to the Animal with an initial status of pending_summarization, and return an upload confirmation response to the Vet within 3 seconds of successful file persistence.
3. WHEN a Vet_Report file is a PDF, THE Vet_Report_Summarizer SHALL extract text content from the PDF before submitting it to the Gemini API.
4. IF a PDF file yields no extractable text content, THEN THE System SHALL mark the Vet_Report status as summary_failed with an error reason of unextractable_pdf_content and SHALL NOT submit the empty content to the Gemini API.
5. WHEN text extraction from a Vet_Report is complete and the extracted text is non-empty, THE Vet_Report_Summarizer SHALL submit the extracted text to the Google Gemini API with a structured prompt requesting a plain-English summary of diagnoses, treatments, and follow-up actions.
6. WHEN the Gemini API returns a successful response, THE Vet_Report_Summarizer SHALL store the response as the plain_english_summary field on the Vet_Report record.
7. IF the Gemini API returns an error or does not respond within 30 seconds, THEN THE System SHALL mark the Vet_Report status as summary_failed and store the error reason in the Vet_Report record.
8. THE Celery_Worker SHALL process Vet_Report summarization asynchronously after the upload response has been returned to the Vet, so that the upload response time is independent of summarization processing duration.
9. WHEN summarization completes successfully, THE System SHALL update the Vet_Report record status to summary_ready and make the plain_english_summary available via the REST_API.
10. THE System SHALL restrict Vet_Report file uploads to files with MIME types application/pdf and text/plain, and SHALL reject all other MIME types with HTTP status 415.
11. THE System SHALL limit uploaded Vet_Report file size to a maximum of 10 MB and return HTTP status 413 for oversized uploads.
12. THE REST_API SHALL expose endpoints to list Vet_Reports by animal_id and retrieve a single Vet_Report by id, including the current status, plain_english_summary (if available), and error_reason (if applicable).

---

### Requirement 7: Cost Optimizer — Feed Cost vs. Milk Yield ROI

**User Story:** As a Farm_Manager, I want to input feed costs and see the milk yield ROI per animal and for the herd, so that I can identify unprofitable animals and optimize feed allocation.

#### Acceptance Criteria

1. WHEN a Farm_Manager creates a feed cost entry, THE Cost_Optimizer SHALL require animal_tag (or a herd-level indicator), date, feed_type, quantity_kg (a positive number greater than zero), and cost_per_kg (a positive number greater than zero), and SHALL reject entries where quantity_kg or cost_per_kg is zero or negative with a field-level validation error.
2. WHEN a feed cost entry is persisted, THE Cost_Optimizer SHALL compute and store total_feed_cost as the product of quantity_kg and cost_per_kg.
3. WHEN ROI is computed for a given date range, THE Cost_Optimizer SHALL compute milk_revenue as the product of total_daily_yield_liters for the period and the farm-level milk_price_per_liter configuration value.
4. WHEN a Farm_Manager requests an ROI calculation, THE Cost_Optimizer SHALL compute ROI_ratio as milk_revenue divided by total_feed_cost for the specified date range and Animal or herd. The date range SHALL be limited to a maximum of 365 days.
5. IF total_feed_cost for a given period is zero, THEN THE Cost_Optimizer SHALL return a response indicating ROI is not calculable rather than performing a division by zero.
6. IF milk_price_per_liter has not been configured at the farm level, THEN THE Cost_Optimizer SHALL return a response indicating that ROI cannot be computed until milk_price_per_liter is configured.
7. WHEN a Farm_Manager requests the ROI endpoint, THE Cost_Optimizer SHALL accept animal_tag (optional), start_date, and end_date, and return total_feed_cost, milk_revenue, ROI_ratio, and daily_breakdown where each entry in daily_breakdown contains date, daily_feed_cost, daily_milk_revenue, and daily_roi_ratio.
8. WHEN a Farm_Manager views the cost optimizer page, THE System SHALL render a Chart.js chart displaying total_feed_cost versus milk_revenue over the selected date range.
9. WHEN a Farm_Manager requests low performers for a given month, THE Cost_Optimizer SHALL return the Animals in the bottom 10% by ROI_ratio sorted ascending by ROI_ratio. IF the herd contains fewer than 10 Animals, THE Cost_Optimizer SHALL return the single Animal with the lowest ROI_ratio.
10. WHEN a Farm_Manager updates the farm-level milk_price_per_liter, THE REST_API SHALL validate that the submitted value is a positive number greater than zero, persist the new value, and apply it to all subsequent ROI computations.

---

### Requirement 8: Breeding Manager — Reproductive Event Tracking and Prediction

**User Story:** As a Farm_Manager, I want to track heat cycles, pregnancies, and AI events for each animal, and receive predicted optimal breeding dates, so that I can maximize conception rates and calving outcomes.

#### Acceptance Criteria

1. WHEN a Farm_Manager creates a Heat_Cycle record, THE Breeding_Manager SHALL require animal_tag (referencing a female Animal) and observed_date, and accept an optional notes field of up to 500 characters.
2. WHEN a Farm_Manager creates an AI_Event record, THE Breeding_Manager SHALL require animal_tag (referencing a female Animal), insemination_date, bull_code, technician_name, and outcome (one of {Pending, Confirmed_Pregnant, Failed}).
3. WHEN a Farm_Manager creates a Pregnancy record, THE Breeding_Manager SHALL require animal_tag (referencing a female Animal) and conception_date, and accept expected_calving_date and actual_calving_date (nullable) as optional fields.
4. IF a Pregnancy record is created without an explicit expected_calving_date, THEN THE Breeding_Manager SHALL compute and store expected_calving_date as conception_date plus 283 days.
5. WHEN a Farm_Manager requests a Breeding_Prediction for a female Animal, THE Breeding_Manager SHALL compute and return the predicted next heat date by adding the configurable inter-heat interval (default 21 days) to the most recent Heat_Cycle observed_date, the recommended insemination window (predicted heat date to predicted heat date plus 18 hours), and a success_probability estimate.
6. IF an Animal has more than 5 historical AI_Event records, THEN THE Breeding_Manager SHALL compute success_probability using a statistical model trained on the Animal's historical AI_Event outcomes.
7. IF an Animal has 5 or fewer historical AI_Event records, THEN THE Breeding_Manager SHALL return a default success_probability of 0.50 and include a boolean low_data_warning: true field in the response indicating the estimate is based on insufficient history.
8. IF a Farm_Manager requests a Breeding_Prediction for an Animal with no recorded Heat_Cycle records, THEN THE Breeding_Manager SHALL return an error response indicating that a predicted heat date cannot be computed without at least one Heat_Cycle record.
9. WHEN a Farm_Manager views the monthly breeding calendar, THE System SHALL display all Animals with predicted heat dates, scheduled AI_Events, and expected calving dates for the selected month.
10. WHEN an AI_Event outcome is updated to Confirmed_Pregnant, THE Breeding_Manager SHALL check whether a Pregnancy record already exists for that Animal with a conception_date within 30 days of the insemination_date. IF no such Pregnancy record exists, THEN THE Breeding_Manager SHALL create a new Pregnancy record using the insemination_date as conception_date.
11. WHEN the Celery_Worker executes the daily scheduled task at 06:00 UTC, THE Breeding_Manager SHALL identify Animals whose predicted next heat date falls within the following 3 days, and for each such Animal that does not already have an unacknowledged Alert of severity Medium created within the past 24 hours for that same predicted heat date, SHALL create a new Alert record of severity Medium.

---

### Requirement 9: Dashboard and Reporting

**User Story:** As a Farm_Manager, I want a single Dashboard page summarizing farm health, production, alerts, and forecasts, so that I can make daily management decisions without navigating multiple pages.

#### Acceptance Criteria

1. WHEN the Dashboard page loads, THE System SHALL display the following KPI cards: total active Animals, today's herd milk yield (sum of all active Animals' total_daily_yield_liters for the current calendar date), count of unacknowledged Alerts, and the herd-level ROI_ratio for the trailing 7 days.
2. WHEN the Dashboard page loads, THE System SHALL render a Chart.js line chart showing the herd's total daily milk yield for the trailing 30 calendar days.
3. WHEN the Dashboard page loads, THE System SHALL display the 5 most recent unacknowledged Alerts ordered by created_at descending, each showing animal_tag, date, severity, and a one-click acknowledge button.
4. WHEN the Dashboard page loads, THE System SHALL display a Chart.js chart for the upcoming 7-day herd Forecast using the most recently stored Forecast data.
5. WHEN the Dashboard page loads, THE System SHALL retrieve all displayed data through REST_API calls to support future mobile client reuse. THE System MAY additionally render critical KPI data server-side as a performance optimization for initial page load.
6. WHEN a Farm_Manager requests a CSV export, THE System SHALL return a downloadable CSV file for Milk_Log data, Alert data, or ROI_Record data, accepting start_date, end_date, and optional animal_tag as filter parameters, and SHALL include a header row with column names.
7. WHEN 10 simultaneous Farm_User sessions request Dashboard data concurrently, THE REST_API SHALL return all Dashboard endpoint responses within 2 seconds.

---

### Requirement 10: Project Structure, API Design, and Infrastructure

**User Story:** As a developer, I want a clearly defined project folder structure, Django app breakdown, MySQL schema, REST API endpoint list, Celery task list, and ML integration points, so that I can implement and maintain the system with minimal ambiguity.

#### Acceptance Criteria

1. THE System SHALL be organized into the following top-level directory structure:

```
dairymind/
├── manage.py
├── requirements.txt
├── .env.example
├── docker-compose.yml
├── dairymind/                  # Django project config
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── celery.py
│   └── wsgi.py
├── apps/
│   ├── accounts/               # Farm_User auth and RBAC
│   ├── cattle/                 # Cattle_Registry
│   ├── milk/                   # Milk_Tracker
│   ├── health/                 # Health_Alert_Engine
│   ├── forecast/               # Forecast_Engine
│   ├── vet_reports/            # Vet_Report_Summarizer
│   ├── costs/                  # Cost_Optimizer
│   └── breeding/               # Breeding_Manager
├── ml/
│   ├── anomaly_detection.py    # Isolation Forest wrapper
│   ├── forecasting.py          # Prophet wrapper
│   └── breeding_model.py       # Logistic regression wrapper
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   └── [per-app templates]
└── static/
    ├── css/
    ├── js/
    └── vendor/
```

#### Django Apps Breakdown

2. THE accounts app SHALL implement Farm_User model extending AbstractUser, role field, token authentication, and login/logout views.
3. THE cattle app SHALL implement the Animal model, AnimalHistory model, and all Cattle_Registry REST_API views.
4. THE milk app SHALL implement the Milk_Log model and all Milk_Tracker REST_API views including bulk creation.
5. THE health app SHALL implement the Alert model, the Health_Alert_Engine integration, and all Alert REST_API views.
6. THE forecast app SHALL implement the Forecast model, the Forecast_Engine integration, and all Forecast REST_API views.
7. THE vet_reports app SHALL implement the Vet_Report model, file upload handling, and the Vet_Report_Summarizer Gemini API integration.
8. THE costs app SHALL implement the FeedCost model, the FarmConfig model (for milk_price_per_liter), and all Cost_Optimizer REST_API views.
9. THE breeding app SHALL implement the HeatCycle, AIEvent, Pregnancy, and BreedingPrediction models and all Breeding_Manager REST_API views.

#### MySQL Schema (Key Tables)

10. THE database SHALL contain the following tables with the specified columns:

```
animals:           id, tag_number (unique), name, breed, dob, gender, status, sire_tag, dam_tag, purchase_date, notes, created_at, updated_at
animal_history:    id, animal_id (FK), changed_by (FK→users), changed_at, previous_values (JSON), changed_fields (JSON)
milk_logs:         id, animal_id (FK), log_date, morning_yield, evening_yield, total_yield, notes, created_at
alerts:            id, animal_id (FK), alert_date, observed_yield, expected_min, expected_max, severity, acknowledged, acknowledged_by (FK→users, nullable), acknowledged_at (nullable), created_at
forecasts:         id, animal_id (FK, nullable for herd), generated_at, forecast_date, predicted_yield, lower_bound, upper_bound
vet_reports:       id, animal_id (FK), uploaded_by (FK→users), uploaded_at, file_path, file_type, plain_english_summary (TEXT, nullable), status, error_reason (nullable)
feed_costs:        id, animal_id (FK, nullable for herd), entry_date, feed_type, quantity_kg, cost_per_kg, total_feed_cost, created_at
farm_config:       id, key (unique), value, updated_by (FK→users), updated_at
heat_cycles:       id, animal_id (FK), observed_date, notes, created_at
ai_events:         id, animal_id (FK), insemination_date, bull_code, technician_name, outcome, created_at, updated_at
pregnancies:       id, animal_id (FK), conception_date, expected_calving_date, actual_calving_date (nullable), created_at, updated_at
breeding_predictions: id, animal_id (FK), predicted_heat_date, insemination_window_end, success_probability, insufficient_history_flag, generated_at
```

#### REST API Endpoints

11. THE REST_API SHALL expose the following endpoints:

```
Authentication
  POST   /api/auth/login/
  POST   /api/auth/logout/

Cattle Registry
  GET    /api/cattle/
  POST   /api/cattle/
  GET    /api/cattle/{id}/
  PUT    /api/cattle/{id}/
  DELETE /api/cattle/{id}/
  GET    /api/cattle/{id}/history/

Milk Tracker
  GET    /api/milk/logs/
  POST   /api/milk/logs/
  POST   /api/milk/logs/bulk/
  GET    /api/milk/herd-summary/?start_date=&end_date=
  GET    /api/milk/animal/{animal_id}/series/?start_date=&end_date=

Health Alerts
  GET    /api/alerts/
  GET    /api/alerts/{id}/
  POST   /api/alerts/{id}/acknowledge/

Forecast
  GET    /api/forecast/herd/
  GET    /api/forecast/animal/{animal_id}/
  POST   /api/forecast/refresh/

Vet Reports
  GET    /api/vet-reports/?animal_id=
  POST   /api/vet-reports/upload/
  GET    /api/vet-reports/{id}/

Cost Optimizer
  GET    /api/costs/feed-entries/
  POST   /api/costs/feed-entries/
  GET    /api/costs/roi/?animal_id=&start_date=&end_date=
  GET    /api/costs/low-performers/?month=
  GET    /api/costs/config/
  PUT    /api/costs/config/

Breeding Manager
  GET    /api/breeding/heat-cycles/?animal_id=
  POST   /api/breeding/heat-cycles/
  GET    /api/breeding/ai-events/?animal_id=
  POST   /api/breeding/ai-events/
  PUT    /api/breeding/ai-events/{id}/
  GET    /api/breeding/pregnancies/?animal_id=
  POST   /api/breeding/pregnancies/
  PUT    /api/breeding/pregnancies/{id}/
  GET    /api/breeding/predictions/?animal_id=
  GET    /api/breeding/calendar/?year=&month=

Dashboard & Exports
  GET    /api/dashboard/summary/
  GET    /api/export/milk-logs/?start_date=&end_date=&animal_id=
  GET    /api/export/alerts/?start_date=&end_date=
  GET    /api/export/roi/?start_date=&end_date=
```

#### Celery Task List

12. THE Celery_Worker SHALL implement the following named tasks:

```
health.tasks.run_anomaly_detection(milk_log_id)
  Triggered: Post-save signal on MilkLog
  Action: Evaluate the new Milk_Log against the Animal's trained Isolation Forest model; create Alert if anomalous

health.tasks.retrain_isolation_forest(animal_id)
  Triggered: When Animal accumulates 50 new Milk_Logs since last training
  Action: Retrain and persist the Isolation Forest model for the Animal

forecast.tasks.generate_all_forecasts()
  Triggered: Nightly cron at 02:00 server time
  Action: Run Prophet forecast for all eligible Animals and the herd; persist results to forecasts table

forecast.tasks.generate_single_forecast(animal_id)
  Triggered: Manual refresh via POST /api/forecast/refresh/
  Action: Run Prophet forecast for a single Animal; persist result

vet_reports.tasks.summarize_vet_report(vet_report_id)
  Triggered: Post-save signal on VetReport
  Action: Extract text, call Gemini API, persist summary or error

breeding.tasks.check_upcoming_heats()
  Triggered: Daily cron at 06:00 server time
  Action: Identify Animals with predicted heat in next 3 days; create Medium severity Alerts
```

#### ML Model Integration Points

13. THE ml/anomaly_detection.py module SHALL expose the following interface:

```python
class IsolationForestModel:
    def train(self, animal_id: int, yield_series: list[float]) -> None
    def predict(self, animal_id: int, yield_value: float) -> dict  # {is_anomaly, expected_min, expected_max, severity}
    def save_model(self, animal_id: int) -> None
    def load_model(self, animal_id: int) -> None
```

14. THE ml/forecasting.py module SHALL expose the following interface:

```python
class ProphetForecaster:
    def fit(self, animal_id: int, date_yield_series: list[dict]) -> None  # [{ds, y}]
    def predict(self, animal_id: int, periods: int = 30) -> list[dict]   # [{ds, yhat, yhat_lower, yhat_upper}]
```

15. THE ml/breeding_model.py module SHALL expose the following interface:

```python
class BreedingSuccessModel:
    def train(self, animal_id: int, ai_event_features: list[dict]) -> None
    def predict_probability(self, animal_id: int, features: dict) -> float
    def has_sufficient_data(self, animal_id: int) -> bool  # True if > 5 AI_Events
```

---

### Requirement 11: Non-Functional Requirements

**User Story:** As a system operator, I want the application to meet defined performance, security, and reliability standards, so that the system remains stable and trustworthy under farm operating conditions.

#### Acceptance Criteria

1. THE REST_API SHALL return all list endpoints within 500ms for datasets up to 10,000 records under a single-user load. Performance degradation beyond 10,000 records is acceptable and not subject to this time constraint.
2. THE System SHALL hash all Farm_User passwords using Django's default PBKDF2 algorithm before storage and SHALL NOT store plaintext passwords.
3. THE System SHALL enforce HTTPS for all REST_API endpoints in production.
4. THE System SHALL validate and sanitize all user-supplied inputs at the serializer layer before any database write operation.
5. THE Celery_Worker SHALL retry failed tasks up to 3 times with an exponential backoff starting at 60 seconds before marking the task as failed.
6. THE System SHALL log all REST_API errors at severity ERROR or above to a structured log output compatible with standard log aggregation tools.
7. WHEN the database connection is unavailable, THE System SHALL return HTTP status 503 with a message indicating temporary unavailability rather than exposing internal stack traces.
8. THE System SHALL store the Google Gemini API key, MySQL credentials, and Redis connection URL exclusively in environment variables and SHALL NOT hardcode these values in source code. WHEN the application starts and any of these required environment variables are absent, THE System SHALL fail fast with a descriptive startup error identifying the missing variables rather than allowing operation without them.
9. THE System SHALL support database migrations managed by Django's migration framework, with no destructive schema changes applied without a reversible migration.
10. THE System SHALL include a docker-compose.yml file defining services for the Django application, MySQL 8.0, Redis, and the Celery_Worker, enabling single-command local environment setup.
