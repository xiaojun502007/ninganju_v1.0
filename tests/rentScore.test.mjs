import assert from "node:assert/strict";
import test from "node:test";
import { calculateRentFitScore, calculateRentOverlapScore } from "../src/utils/rentScore.ts";

const context = (rentMin, rentMax) => ({
  budgetMin: 1800,
  budgetMax: 2500,
  housingType: "一居室普通住宅",
  rentMin,
  rentMax
});

test("scores overlap against the user's budget interval", () => {
  assert.equal(calculateRentOverlapScore(context(2290, 2800)).score, 60);
  assert.equal(calculateRentOverlapScore(context(2150, 2800)).score, 70);
  assert.equal(calculateRentOverlapScore(context(2080, 2800)).score, 80);
  assert.equal(calculateRentOverlapScore(context(2010, 2800)).score, 90);
  assert.equal(calculateRentOverlapScore(context(1940, 2800)).score, 90);
  assert.equal(calculateRentOverlapScore(context(1870, 2800)).score, 100);
  assert.equal(calculateRentOverlapScore(context(1800, 2500)).score, 100);
});

test("does not invent a score when rent range is missing", () => {
  assert.equal(calculateRentOverlapScore(context(null, null)), null);
  assert.equal(calculateRentFitScore(90, 80, null), null);
});

test("total uses 40% commute, 30% facilities, and 30% rent", () => {
  assert.equal(calculateRentFitScore(100, 85, 70), 87);
});
