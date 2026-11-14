//! The presets built into the binary.

use crate::layer::{Layer, Profile};
use crate::policy::PolicyError;

const COMMON: &str = include_str!("../presets/common.toml");
const OBSERVE: &str = include_str!("../presets/observe.toml");
const GUARDED: &str = include_str!("../presets/guarded.toml");
const STRICT: &str = include_str!("../presets/strict.toml");
const UNATTENDED: &str = include_str!("../presets/unattended.toml");
const SHELF: &str = include_str!("../presets/shelf.toml");

/// The text of the preset of a profile.
#[must_use]
pub const fn text(profile: Profile) -> &'static str {
    match profile {
        Profile::Observe => OBSERVE,
        Profile::Guarded => GUARDED,
        Profile::Strict => STRICT,
        Profile::Unattended => UNATTENDED,
        Profile::Shelf => SHELF,
    }
}

/// The layers of a profile's preset: what every profile shares, then the profile's own.
pub fn layers(profile: Profile) -> Result<Vec<(String, Layer)>, PolicyError> {
    let read = |name: String, text: &str| -> Result<(String, Layer), PolicyError> {
        Layer::parse(text)
            .map(|layer| (name.clone(), layer))
            .map_err(|message| PolicyError::Preset(format!("{name}: {message}")))
    };
    Ok(vec![read("preset:common".to_owned(), COMMON)?, read(format!("preset:{}", profile.name()), text(profile))?])
}
