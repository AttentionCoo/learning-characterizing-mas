package com.learnagent.controller;

import com.learnagent.entity.Result;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/courses")
@RequiredArgsConstructor
public class CourseController {

    @GetMapping
    public Result getCourseList(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String category) {
        List<Map<String, Object>> courses = new ArrayList<>();
        Map<String, Object> course = new HashMap<>();
        course.put("courseId", 1);
        course.put("name", "脑卒中诊�?);
        course.put("category", "临床医学");
        course.put("description", "涵盖脑卒中的诊断、治疗与预防");
        course.put("knowledgePointCount", 45);
        course.put("totalEstimatedHours", 60);
        courses.add(course);

        Map<String, Object> data = new HashMap<>();
        data.put("total", courses.size());
        data.put("records", courses);
        return Result.success(data);
    }

    @GetMapping("/{courseId}/knowledge-tree")
    public Result getKnowledgeTree(@PathVariable Long courseId) {
        Map<String, Object> tree = new HashMap<>();
        tree.put("courseId", courseId);
        tree.put("name", "脑卒中诊�?);

        Map<String, Object> rootNode = new HashMap<>();
        rootNode.put("id", "root");
        rootNode.put("name", "脑卒中诊�?);
        rootNode.put("children", List.of(
                Map.of("id", "ch1", "name", "神经解剖�?, "children", List.of(
                        Map.of("id", "k1", "name", "脑的血液供�?, "difficulty", "intermediate"),
                        Map.of("id", "k2", "name", "Willis�?, "difficulty", "advanced")
                )),
                Map.of("id", "ch2", "name", "脑血管疾�?, "children", List.of(
                        Map.of("id", "k3", "name", "缺血性脑卒中", "difficulty", "intermediate"),
                        Map.of("id", "k4", "name", "静脉溶栓", "difficulty", "advanced")
                ))
        ));
        tree.put("tree", rootNode);
        return Result.success(tree);
    }
}