//! Keeps credentials and personal data away from a model.
//!
//! [`Redactor`] finds secrets and personal data in text and replaces each by a stable token such as `<EMAIL_1>`; a
//! [`Session`] remembers which value each token stands for, so that [`Redactor::restore`] can put the original value
//! back when the agent later writes the token into a file.

#![cfg_attr(test, allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing))]

mod config;
mod counts;
mod detect;
mod kind;
mod redactor;
mod session;

pub use config::{Config, CustomPattern, PiiConfig};
pub use counts::Counts;
pub use kind::Kind;
pub use redactor::{Hit, LineRedactor, Redactor};
pub use session::Session;
