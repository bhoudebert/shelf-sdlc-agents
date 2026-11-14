use std::collections::BTreeMap;

/// How many values each detector replaced, by detector name (`aws_access_key`, `email`, ...).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Counts {
    by_detector: BTreeMap<String, usize>,
}

impl Counts {
    /// An empty tally.
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    /// Counts one more replacement by `detector`.
    pub fn add(&mut self, detector: &str) {
        *self.by_detector.entry(detector.to_owned()).or_insert(0) += 1;
    }

    /// Adds every count of `other` to this tally.
    pub fn merge(&mut self, other: &Counts) {
        for (detector, n) in &other.by_detector {
            *self.by_detector.entry(detector.clone()).or_insert(0) += n;
        }
    }

    /// The number of replacements over all detectors.
    #[must_use]
    pub fn total(&self) -> usize {
        self.by_detector.values().sum()
    }

    /// Whether nothing was replaced.
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.by_detector.is_empty()
    }

    /// The detectors and their counts, ordered by detector name.
    pub fn iter(&self) -> impl Iterator<Item = (&str, usize)> {
        self.by_detector.iter().map(|(name, n)| (name.as_str(), *n))
    }
}
