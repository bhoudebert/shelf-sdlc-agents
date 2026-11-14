use serde::{Deserialize, Serialize};

/// What a redacted value is; it decides the prefix of its token.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    /// A credential: key, token, password, private key.
    Secret,
    /// An email address.
    Email,
    /// A phone number.
    Phone,
    /// An IBAN bank account number.
    Iban,
    /// A payment card number.
    Card,
    /// A French social security number (NIR).
    Nir,
    /// A US social security number.
    Ssn,
    /// A public IPv4 address.
    Ip,
    /// The name of a person.
    Person,
    /// A value found by a user-supplied pattern, named by the user.
    Custom(String),
}

impl Kind {
    /// The prefix of the tokens of this kind: `SECRET`, `EMAIL`, ...; for a custom kind its name in upper case with
    /// every character that is not a letter or a digit replaced by `_`.
    #[must_use]
    pub fn prefix(&self) -> String {
        match self {
            Self::Secret => "SECRET".to_owned(),
            Self::Email => "EMAIL".to_owned(),
            Self::Phone => "PHONE".to_owned(),
            Self::Iban => "IBAN".to_owned(),
            Self::Card => "CARD".to_owned(),
            Self::Nir => "NIR".to_owned(),
            Self::Ssn => "SSN".to_owned(),
            Self::Ip => "IP".to_owned(),
            Self::Person => "PERSON".to_owned(),
            Self::Custom(name) => {
                name.chars().map(|c| if c.is_ascii_alphanumeric() { c.to_ascii_uppercase() } else { '_' }).collect()
            }
        }
    }
}
