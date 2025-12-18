
resource "pagerduty_service_dependency" "dep_D2GM4S41FVBI9NQYPH7" {
  dependency {
    dependent_service {
      id   = "PA7HPI0"
      type = "service"
    }
    supporting_service {
      id   = "PJ4Q6F2"
      type = "service"
    }
  }
}

resource "pagerduty_service_dependency" "dep_D2GM4TER8JNUZPCH11Z" {
  dependency {
    dependent_service {
      id   = "PJSUJGC"
      type = "business_service"
    }
    supporting_service {
      id   = "PA7HPI0"
      type = "service"
    }
  }
}
