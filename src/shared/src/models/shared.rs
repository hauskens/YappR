use std::str::FromStr;

#[derive(Debug, Clone)]
pub enum Environment {
    Dev,
    Prod,
    Staging,
}

impl FromStr for Environment {
    type Err = String;
    
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "dev" => Ok(Environment::Dev),
            "staging" => Ok(Environment::Staging),
            "prod" => Ok(Environment::Prod),
            _ => Err(format!("Invalid environment: {}", s))
        }
    }
}
    
impl Environment {
    // Convert to string
    pub fn as_str(&self) -> &str {
        match self {
            Environment::Dev => "dev",
            Environment::Prod => "prod",
            Environment::Staging => "staging",
        }
    }
    
    // Check if production
    pub fn is_prod(&self) -> bool {
        matches!(self, Environment::Prod)
    }
}