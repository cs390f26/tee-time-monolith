# Git & GitHub Collaboration Guide

This document covers how the two of us used Git and GitHub to work together on the **Tee Time** project without stepping on each other's toes or messing up the codebase.

---

## 1. How We Split Up the Work

Since it was just the two of us, we wanted a simple system that kept us moving fast without running into annoying merge conflicts:

* **Task Hand-offs:** Instead of both of us editing the exact same files at the same time, we broke the project into clear tasks and took turns driving. One person would handle a set of features or fixes, wrap it up, and then pass the torch to the other.
* **Staying in Sync:** Before starting a new task, whoever was up next would always pull the latest changes from GitHub (`git pull origin main`) so we were always building on top of clean, up-to-date code.

---

## 2. Our Branching Strategy

We kept our repository structure simple and easy to track:

* **`main` Branch:** Our stable version of the app. We made sure `main` was always working and test-passing.

---

## 3. Pull Requests & Testing

Before merging anything back into `main`, we followed a quick routine:

1. **Local Check:** Run `pytest` locally to make sure all tests pass and coverage stays high.
2. **Push to Main:** Push the changes made to the main branch.
3. **Review** The other partner reviews the changes that were made.

---

## 4. Avoiding Merge Conflicts

Because we communicated closely and took turns working on core sections of the code, we almost never had to deal with complex merge conflicts. Whenever small updates overlapped, we just rebased or merged `main` into our active feature branch before pushing.