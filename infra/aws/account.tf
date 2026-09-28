# Settings of the account itself rather than of one resource.

# Every new EBS disk in this region is encrypted, whoever creates it.
resource "aws_ebs_encryption_by_default" "on" {
  enabled = true
}

# The billing alarm, set before anything else in Phase 06. The account is on
# AWS's free plan, which cannot be charged, so this guards the credits:
# running out of them closes the account early. Credits are excluded, or they
# would cancel the usage and the budget would always read zero.
resource "aws_budgets_budget" "monthly" {
  name              = "psells-monthly-15"
  budget_type       = "COST"
  limit_amount      = "15.0"
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "2026-09-01_00:00"

  # Costs as billed, before any discount is spread across the month.
  metrics = ["UnblendedCost"]

  filter_expression {
    not {
      dimensions {
        key    = "RECORD_TYPE"
        values = ["Credit"]
      }
    }
  }

  dynamic "notification" {
    for_each = {
      actual_50   = { type = "ACTUAL", threshold = 50 }
      actual_80   = { type = "ACTUAL", threshold = 80 }
      actual_100  = { type = "ACTUAL", threshold = 100 }
      forecast100 = { type = "FORECASTED", threshold = 100 }
    }

    content {
      notification_type          = notification.value.type
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value.threshold
      threshold_type             = "PERCENTAGE"
      subscriber_email_addresses = [var.alert_email]
    }
  }
}
