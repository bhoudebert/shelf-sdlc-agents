//! The policy of Warden: what a finding is called, what to do about it, and how layers of policy files combine.
#![cfg_attr(test, allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing))]

pub mod category;
pub mod layer;
pub mod policy;
pub mod presets;

pub use category::{Category, Decision};
pub use layer::{Layer, Mode, OnError, Profile};
pub use policy::{Network, PathSet, Paths, Policy, PolicyError, Rewrite, Rule};
