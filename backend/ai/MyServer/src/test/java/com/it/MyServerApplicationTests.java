package com.it;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@Disabled("Skipped because Redis/MySQL services are not running locally")
class MyServerApplicationTests {

    @Test
    void contextLoads() {
    }

}